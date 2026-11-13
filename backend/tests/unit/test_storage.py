"""T05 🧪：M3 存储抽象。

DEVPLAN 要求的两项：
- 路径穿越（../、绝对路径、符号链接）被拒绝
- 中途失败不残留临时文件
"""

import hashlib
import io
import os
import re
import uuid
import zipfile
from datetime import UTC, datetime

import pytest

from app.modules.storage import (
    EmptyFileError,
    FileTooLargeError,
    InvalidStorageKeyError,
    LocalStorage,
    StorageError,
    StoredFileNotFoundError,
    UnsupportedFileTypeError,
    detect_file_type,
)

DOC_ID = uuid.UUID("11111111-2222-4333-8444-555555555555")
PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32

DOCX_MAIN = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
XLSX_MAIN = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
DOCM_MAIN = "application/vnd.ms-word.document.macroEnabled.main+xml"


def ooxml_bytes(main_content_type: str | None, part_name: str = "word/document.xml") -> bytes:
    """造一个最小的 Office zip 包；main_content_type=None 时不写 [Content_Types].xml。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if main_content_type is not None:
            zf.writestr(
                "[Content_Types].xml",
                '<?xml version="1.0"?><Types><Override '
                f'PartName="/{part_name}" ContentType="{main_content_type}"/></Types>',
            )
        zf.writestr(part_name, "<x/>")
    return buf.getvalue()


@pytest.fixture
def root(tmp_path):
    return tmp_path / "storage"


@pytest.fixture
def storage(root):
    return LocalStorage(root)


def temp_files(root):
    return list((root / ".tmp").iterdir())


def all_files(root):
    return [p for p in root.rglob("*") if p.is_file() or p.is_symlink()]


# ---- 正常路径 ----


def test_put_stores_file_at_generated_path(storage, root):
    stored = storage.put(io.BytesIO(PDF_BYTES), document_id=DOC_ID)

    sha = hashlib.sha256(PDF_BYTES).hexdigest()
    year = datetime.now(UTC).year
    assert stored.storage_key == f"{year}/{DOC_ID}/{sha}.pdf"
    assert stored.sha256 == sha
    assert stored.size == len(PDF_BYTES)
    assert stored.mime_type == "application/pdf"
    assert (root / stored.storage_key).read_bytes() == PDF_BYTES
    assert temp_files(root) == []


def test_open_returns_content(storage):
    stored = storage.put(io.BytesIO(PDF_BYTES), document_id=DOC_ID)

    with storage.open(stored.storage_key) as f:
        assert f.read() == PDF_BYTES


def test_stage_does_not_touch_final_path_until_commit(storage, root):
    staged = storage.stage(io.BytesIO(PDF_BYTES), document_id=DOC_ID)

    assert not (root / staged.storage_key).exists()
    assert len(temp_files(root)) == 1

    stored = storage.commit(staged)

    assert stored.storage_key == staged.storage_key
    assert (root / stored.storage_key).read_bytes() == PDF_BYTES
    assert temp_files(root) == []


def test_discard_removes_staged_file_and_is_repeatable(storage, root):
    staged = storage.stage(io.BytesIO(PDF_BYTES), document_id=DOC_ID)

    storage.discard(staged)
    storage.discard(staged)

    assert all_files(root) == []


def test_put_same_content_twice_is_idempotent(storage, root):
    first = storage.put(io.BytesIO(PDF_BYTES), document_id=DOC_ID)
    second = storage.put(io.BytesIO(PDF_BYTES), document_id=DOC_ID)

    assert first == second
    assert len(all_files(root)) == 1


def test_delete_removes_file_and_empty_directories(storage, root):
    stored = storage.put(io.BytesIO(PDF_BYTES), document_id=DOC_ID)

    storage.delete(stored.storage_key)

    assert all_files(root) == []
    assert not (root / stored.storage_key).parent.exists()
    with pytest.raises(StoredFileNotFoundError):
        storage.open(stored.storage_key)


def test_delete_missing_file_is_a_noop(storage):
    stored = storage.put(io.BytesIO(PDF_BYTES), document_id=DOC_ID)

    storage.delete(stored.storage_key)
    storage.delete(stored.storage_key)


def test_delete_keeps_year_directory_used_by_other_documents(storage, root):
    other_id = uuid.UUID("99999999-2222-4333-8444-555555555555")
    stored = storage.put(io.BytesIO(PDF_BYTES), document_id=DOC_ID)
    other = storage.put(io.BytesIO(PNG_BYTES), document_id=other_id)

    storage.delete(stored.storage_key)

    assert (root / other.storage_key).read_bytes() == PNG_BYTES


# ---- 魔数校验 ----


@pytest.mark.parametrize(
    ("content", "ext", "mime"),
    [
        (PDF_BYTES, "pdf", "application/pdf"),
        (PNG_BYTES, "png", "image/png"),
        (JPEG_BYTES, "jpg", "image/jpeg"),
        (
            ooxml_bytes(DOCX_MAIN),
            "docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        (
            ooxml_bytes(XLSX_MAIN, "xl/workbook.xml"),
            "xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
    ],
)
def test_supported_types_detected_by_content(storage, content, ext, mime):
    stored = storage.put(io.BytesIO(content), document_id=DOC_ID)

    assert stored.storage_key.endswith(f".{ext}")
    assert stored.mime_type == mime


@pytest.mark.parametrize(
    "content",
    [
        b"just some plain text, renamed to report.pdf by the user\n",
        b"MZ\x90\x00" + b"\x00" * 64,  # Windows 可执行文件
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64,  # 旧版 .doc / .xls（OLE）
        b"GIF89a" + b"\x00" * 32,
        b"  %PDF-1.4\n",  # 魔数不在文件开头
        ooxml_bytes(None),  # 普通 zip，没有 [Content_Types].xml
        ooxml_bytes(DOCM_MAIN),  # 带宏的 Word 文档
        b"PK\x03\x04" + b"\x00" * 64,  # 只有 zip 文件头，结构损坏
    ],
    ids=["text", "exe", "ole", "gif", "pdf-not-at-start", "plain-zip", "docm", "broken-zip"],
)
def test_unsupported_content_rejected_and_nothing_left(storage, root, content):
    with pytest.raises(UnsupportedFileTypeError):
        storage.put(io.BytesIO(content), document_id=DOC_ID)

    assert all_files(root) == []


def test_oversized_content_types_part_rejected(tmp_path):
    # [Content_Types].xml 超过 1 MB：按 zip 炸弹处理，不读完、不识别
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", DOCX_MAIN + " " * (2 * 1024 * 1024))
    path = tmp_path / "bomb.docx"
    path.write_bytes(buf.getvalue())

    assert detect_file_type(path) is None


# ---- 🧪 路径穿越被拒绝 ----

VALID_SHA = "a" * 64
YEAR = "2026"

BAD_KEYS = [
    "",
    "../secret.pdf",
    f"../{YEAR}/{DOC_ID}/{VALID_SHA}.pdf",
    f"{YEAR}/../{DOC_ID}/{VALID_SHA}.pdf",
    f"{YEAR}/{DOC_ID}/../../../etc/passwd",
    f"{YEAR}/{DOC_ID}/../{VALID_SHA}.pdf",
    "/etc/passwd",
    f"/{YEAR}/{DOC_ID}/{VALID_SHA}.pdf",
    f"{YEAR}/{DOC_ID}/{VALID_SHA}.pdf/",
    f"{YEAR}//{DOC_ID}/{VALID_SHA}.pdf",
    f"{YEAR}\\{DOC_ID}\\{VALID_SHA}.pdf",
    f"{YEAR}/{DOC_ID}/{VALID_SHA}.pdf\n",
    f"{YEAR}/{DOC_ID}/{VALID_SHA}.pdf\x00",
    f"{YEAR}/{DOC_ID}/{VALID_SHA}.exe",
    f"{YEAR}/{DOC_ID}/{VALID_SHA}",
    f"{YEAR}/ABCDEF12-2222-4333-8444-555555555555/{VALID_SHA}.pdf",  # 大写 UUID
    f"{YEAR}/not-a-uuid/{VALID_SHA}.pdf",
    f"{YEAR}/{DOC_ID}/report.pdf",
    f".tmp/{'a' * 32}.part",
    f"２０２６/{DOC_ID}/{VALID_SHA}.pdf",  # 全角数字
]


@pytest.mark.parametrize("key", BAD_KEYS, ids=[repr(k)[:40] for k in BAD_KEYS])
def test_malformed_keys_rejected_by_open_and_delete(storage, key):
    with pytest.raises(InvalidStorageKeyError):
        storage.open(key)
    with pytest.raises(InvalidStorageKeyError):
        storage.delete(key)


def test_file_symlink_pointing_outside_rejected(storage, root, tmp_path):
    secret = tmp_path / "secret.pdf"
    secret.write_bytes(b"outside the storage root")
    key = f"{YEAR}/{DOC_ID}/{VALID_SHA}.pdf"
    (root / key).parent.mkdir(parents=True)
    (root / key).symlink_to(secret)

    with pytest.raises(InvalidStorageKeyError):
        storage.open(key)
    with pytest.raises(InvalidStorageKeyError):
        storage.delete(key)

    assert secret.read_bytes() == b"outside the storage root"


@pytest.mark.parametrize("level", ["year", "document"])
def test_directory_symlink_pointing_outside_rejected(storage, root, tmp_path, level):
    outside = tmp_path / "outside"
    key = f"{YEAR}/{DOC_ID}/{VALID_SHA}.pdf"
    if level == "year":
        (outside / str(DOC_ID)).mkdir(parents=True)
        victim = outside / str(DOC_ID) / f"{VALID_SHA}.pdf"
        (root / YEAR).symlink_to(outside, target_is_directory=True)
    else:
        outside.mkdir()
        victim = outside / f"{VALID_SHA}.pdf"
        (root / YEAR).mkdir()
        (root / YEAR / str(DOC_ID)).symlink_to(outside, target_is_directory=True)
    victim.write_bytes(b"outside the storage root")

    with pytest.raises(InvalidStorageKeyError):
        storage.open(key)
    with pytest.raises(InvalidStorageKeyError):
        storage.delete(key)

    assert victim.read_bytes() == b"outside the storage root"


def test_put_refuses_to_write_through_directory_symlink(storage, root, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    year = str(datetime.now(UTC).year)
    (root / year).symlink_to(outside, target_is_directory=True)

    with pytest.raises(InvalidStorageKeyError):
        storage.put(io.BytesIO(PDF_BYTES), document_id=DOC_ID)

    assert list(outside.iterdir()) == []
    assert temp_files(root) == []


def test_symlinked_temp_directory_refused_at_startup(tmp_path):
    root = tmp_path / "storage"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / ".tmp").symlink_to(outside, target_is_directory=True)

    with pytest.raises(StorageError):
        LocalStorage(root)


def test_storage_key_never_contains_user_supplied_text(storage):
    # put() 根本不接收文件名：路径只由年份、document_id、sha256 和识别出的扩展名组成
    stored = storage.put(io.BytesIO(PDF_BYTES), document_id=DOC_ID)

    assert re.fullmatch(r"\d{4}/[0-9a-f-]{36}/[0-9a-f]{64}\.pdf", stored.storage_key)


# ---- 🧪 中途失败不残留临时文件 ----


class FailingStream:
    """先给出一部分数据，然后模拟连接中断。"""

    def __init__(self, first_chunk: bytes) -> None:
        self._chunks = [first_chunk]

    def read(self, _size: int = -1) -> bytes:
        if self._chunks:
            return self._chunks.pop()
        raise ConnectionError("client disconnected")


def test_stream_failure_leaves_nothing(storage, root):
    with pytest.raises(ConnectionError):
        storage.put(FailingStream(PDF_BYTES), document_id=DOC_ID)

    assert all_files(root) == []


def test_too_large_leaves_nothing(storage, root):
    with pytest.raises(FileTooLargeError) as excinfo:
        storage.put(io.BytesIO(PDF_BYTES), document_id=DOC_ID, max_size=len(PDF_BYTES) - 1)

    assert excinfo.value.max_size == len(PDF_BYTES) - 1
    assert all_files(root) == []


def test_exactly_max_size_accepted(storage):
    stored = storage.put(io.BytesIO(PDF_BYTES), document_id=DOC_ID, max_size=len(PDF_BYTES))

    assert stored.size == len(PDF_BYTES)


def test_empty_file_leaves_nothing(storage, root):
    with pytest.raises(EmptyFileError):
        storage.put(io.BytesIO(b""), document_id=DOC_ID)

    assert all_files(root) == []


def test_failed_move_leaves_nothing(storage, root, monkeypatch):
    staged = storage.stage(io.BytesIO(PDF_BYTES), document_id=DOC_ID)

    def broken_replace(_src, _dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken_replace)

    with pytest.raises(OSError, match="disk full"):
        storage.commit(staged)

    assert all_files(root) == []


def test_forged_staged_token_rejected(storage):
    staged = storage.stage(io.BytesIO(PDF_BYTES), document_id=DOC_ID)
    forged = type(staged)(
        token="../../etc/passwd",
        storage_key=staged.storage_key,
        sha256=staged.sha256,
        size=staged.size,
        mime_type=staged.mime_type,
    )

    with pytest.raises(InvalidStorageKeyError):
        storage.commit(forged)
    with pytest.raises(InvalidStorageKeyError):
        storage.discard(forged)
