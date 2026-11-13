"""T08：文档管理中不需要数据库就能验证的部分。

- 文件名、标签的规范化
- 上传失败时不留半成品（用假的数据库会话模拟各个步骤失败）
- 未登录 401、Content-Length 超限 413

需要真实数据库的部分（上传入库、列表、删除、共享、标签、任务）在
tests/integration/test_documents.py。
"""

import io
import socket
import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.documents import _content_disposition
from app.config import Settings
from app.core.errors import (
    FileTooLargeError,
    RequestInvalidError,
    UnsupportedFileTypeError,
)
from app.db.models import Document, ProcessingTask, User
from app.main import create_app
from app.modules.documents.service import UploadLimits, clean_filename, upload_document
from app.modules.documents.tags import normalize_tags
from app.modules.storage import LocalStorage

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
LIMITS = UploadLimits(
    max_bytes=1024, max_filename_chars=50, allowed_extensions=frozenset({"pdf", "png"})
)

# ---- 文件名 ----


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("report.pdf", "report.pdf"),
        ("年度报告 2026.pdf", "年度报告 2026.pdf"),
        ("  padded.pdf  ", "padded.pdf"),
        ("C:\\Users\\barry\\Desktop\\report.pdf", "report.pdf"),
        ("/home/barry/report.pdf", "report.pdf"),
        ("../../etc/passwd", "passwd"),
        ("line\r\nbreak\x00.pdf", "linebreak.pdf"),
    ],
)
def test_clean_filename(raw, expected):
    assert clean_filename(raw, 50) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "/", "a/..", ".", "\x00\x01", "x" * 51])
def test_clean_filename_rejects(raw):
    with pytest.raises(RequestInvalidError):
        clean_filename(raw, 50)


def test_clean_filename_length_counts_characters_not_bytes():
    # 50 个汉字是 150 个字节，但仍在 50 个字符的上限之内
    assert clean_filename("报" * 50, 50) == "报" * 50


# ---- 标签 ----


def test_normalize_tags_strips_and_deduplicates_keeping_order():
    assert normalize_tags([" 财务 ", "2026", "财务", "2026 "]) == ["财务", "2026"]
    assert normalize_tags([]) == []


@pytest.mark.parametrize(
    "raw",
    [[""], ["  "], ["x" * 65], ["a\nb"], [f"t{i}" for i in range(21)]],
    ids=["empty", "blank", "too-long", "control-char", "too-many"],
)
def test_normalize_tags_rejects(raw):
    with pytest.raises(RequestInvalidError):
        normalize_tags(raw)


def test_normalize_tags_accepts_limits_exactly():
    assert len(normalize_tags([f"t{i}" for i in range(20)])) == 20
    assert normalize_tags(["x" * 64]) == ["x" * 64]


# ---- 下载响应头 ----


def test_content_disposition_carries_non_ascii_name_safely():
    header = _content_disposition('年度"报告".pdf')

    header.encode("latin-1")  # HTTP 头必须能用 latin-1 编码，否则服务器发不出去
    assert header.startswith('attachment; filename="__')
    assert "filename*=UTF-8''%E5%B9%B4%E5%BA%A6%22%E6%8A%A5%E5%91%8A%22.pdf" in header


def test_content_disposition_cannot_be_broken_out_of():
    header = _content_disposition('a"; filename="evil.exe')

    # 引号被替换，无法提前结束 filename="..." 再注入第二个参数
    assert header.count('"') == 2


# ---- 配置 ----

BASE = {
    "_env_file": None,
    "database_url": "postgresql://u:p@localhost:5432/db",
    "opensearch_url": "http://localhost:9200",
    "clip_service_url": "http://localhost:8001",
    "jwt_secret": "unit-test-secret-not-used-anywhere-else-0123456789",
}


def test_upload_defaults():
    settings = Settings(**BASE)

    assert settings.upload_max_bytes == 50 * 1024 * 1024
    assert settings.upload_max_filename_chars == 255
    assert settings.upload_allowed_extensions == {"pdf", "docx", "xlsx", "png", "jpg"}


def test_upload_allowed_types_parsed_and_validated():
    assert Settings(**BASE, upload_allowed_types=" PDF, png ").upload_allowed_extensions == {
        "pdf",
        "png",
    }
    for bad in ["", "pdf,exe", "doc"]:
        with pytest.raises(ValueError):
            Settings(**BASE, upload_allowed_types=bad)


# ---- 🧪 上传中途失败不留半成品 ----


class FakeSession:
    """记录调用顺序的假数据库会话；可以让 flush 或 commit 失败。"""

    def __init__(self, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.calls: list[str] = []
        self.added: list[object] = []

    def _step(self, name: str) -> None:
        self.calls.append(name)
        if self.fail_on == name:
            raise RuntimeError(f"database failed during {name}")

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self._step("flush")

    def execute(self, _statement: object) -> None:
        self._step("execute")

    def commit(self) -> None:
        self._step("commit")

    def rollback(self) -> None:
        self.calls.append("rollback")


@pytest.fixture
def root(tmp_path):
    return tmp_path / "storage"


@pytest.fixture
def storage(root):
    return LocalStorage(root)


@pytest.fixture
def user() -> User:
    return User(id=uuid.uuid4(), username="barry", password_hash="x", role="user")


def stored_files(root):
    return [p for p in root.rglob("*") if p.is_file()]


def upload(session, storage, user, content=PDF_BYTES, filename="a.pdf", limits=LIMITS):
    return upload_document(
        session,
        storage,
        user,
        stream=io.BytesIO(content),
        filename=filename,
        tags=[],
        limits=limits,
    )


def test_successful_upload_moves_file_before_committing(storage, root, user):
    session = FakeSession()

    document = upload(session, storage, user)

    assert [type(obj) for obj in session.added] == [Document, ProcessingTask]
    task = session.added[1]
    assert task.task_type == "parse"
    assert task.document_id == document.id
    assert document.owner_id == user.id
    assert document.status == "pending"
    assert document.mime_type == "application/pdf"
    assert document.size_bytes == len(PDF_BYTES)
    assert (root / document.storage_key).read_bytes() == PDF_BYTES
    assert stored_files(root) == [root / document.storage_key]
    # 提交是最后一步，且没有回滚
    assert session.calls[-1] == "commit"
    assert "rollback" not in session.calls


@pytest.mark.parametrize(
    ("content", "filename", "error"),
    [
        (PDF_BYTES + b"x" * 2000, "big.pdf", FileTooLargeError),
        (b"plain text renamed to .pdf", "fake.pdf", UnsupportedFileTypeError),
        (b"", "empty.pdf", RequestInvalidError),
        (PDF_BYTES, "x" * 51 + ".pdf", RequestInvalidError),
    ],
    ids=["too-large", "fake-extension", "empty", "filename-too-long"],
)
def test_rejected_upload_leaves_no_file_and_never_touches_database(
    storage, root, user, content, filename, error
):
    session = FakeSession()

    with pytest.raises(error):
        upload(session, storage, user, content=content, filename=filename)

    assert stored_files(root) == []
    assert session.calls == []
    assert session.added == []


def test_recognised_type_outside_allowed_list_is_rejected(storage, root, user):
    session = FakeSession()
    only_pdf = UploadLimits(
        max_bytes=1024, max_filename_chars=50, allowed_extensions=frozenset({"pdf"})
    )

    with pytest.raises(UnsupportedFileTypeError):
        upload(session, storage, user, content=PNG_BYTES, filename="a.png", limits=only_pdf)

    assert stored_files(root) == []
    assert session.calls == []


def test_error_statuses_match_the_api_contract():
    assert FileTooLargeError("x").status_code == 413
    assert UnsupportedFileTypeError("x").status_code == 415
    assert RequestInvalidError("x").status_code == 422


@pytest.mark.parametrize("failing_step", ["flush", "execute", "commit"])
def test_database_failure_leaves_no_file(storage, root, user, failing_step):
    # commit 失败是最要紧的一种：此时文件已经移动到正式路径，必须被删掉
    session = FakeSession(fail_on=failing_step)

    with pytest.raises(RuntimeError, match="database failed"):
        upload(session, storage, user)

    assert stored_files(root) == []
    assert session.calls[-1] == "rollback"


def test_failed_move_rolls_back_database_and_leaves_no_file(storage, root, user, monkeypatch):
    session = FakeSession()

    def broken_commit(_staged):
        raise OSError("disk full")

    monkeypatch.setattr(storage, "commit", broken_commit)

    with pytest.raises(OSError, match="disk full"):
        upload(session, storage, user)

    assert stored_files(root) == []
    assert "commit" not in session.calls
    assert session.calls[-1] == "rollback"


# ---- HTTP：不需要数据库的部分 ----


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def client(tmp_path):
    port = _closed_port()
    settings = Settings(
        _env_file=None,
        database_url=f"postgresql://u:secret-pw@127.0.0.1:{port}/db",
        opensearch_url=f"http://127.0.0.1:{port}",
        clip_service_url=f"http://127.0.0.1:{port}",
        jwt_secret="unit-test-secret-not-used-anywhere-else-0123456789",
        storage_root=tmp_path / "storage",
        upload_max_bytes=1024,
    )
    with TestClient(create_app(settings)) as c:
        yield c


DOC = "11111111-2222-4333-8444-555555555555"

PROTECTED_ROUTES = [
    ("GET", "/api/documents"),
    ("GET", f"/api/documents/{DOC}"),
    ("GET", f"/api/documents/{DOC}/download"),
    ("DELETE", f"/api/documents/{DOC}"),
    ("GET", f"/api/documents/{DOC}/shares"),
    ("POST", f"/api/documents/{DOC}/shares"),
    ("DELETE", f"/api/documents/{DOC}/shares/{DOC}"),
    ("PUT", f"/api/documents/{DOC}/tags"),
    ("GET", "/api/tags"),
    ("GET", f"/api/documents/{DOC}/tasks"),
    ("POST", f"/api/tasks/{DOC}/retry"),
    ("GET", "/api/tasks"),
]


@pytest.mark.parametrize(("method", "path"), PROTECTED_ROUTES)
def test_every_route_requires_login(client, method, path):
    body = {"username": "alice", "tags": []} if method in {"POST", "PUT"} else None

    resp = client.request(method, path, json=body)

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


def test_upload_requires_login(client, tmp_path):
    resp = client.post("/api/documents", files={"file": ("a.pdf", PDF_BYTES, "application/pdf")})

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"
    assert stored_files(tmp_path / "storage") == []


def test_oversized_upload_is_rejected_from_content_length(client, tmp_path):
    # 上限 1 KB；请求体约 1.1 MB，超过“上限 + 表单余量”，在读请求体之前就被拒绝
    huge = b"%PDF-1.4\n" + b"x" * (1100 * 1024)

    resp = client.post("/api/documents", files={"file": ("a.pdf", huge, "application/pdf")})

    assert resp.status_code == 413
    assert resp.json() == {
        "error": {"code": "FILE_TOO_LARGE", "message": "文件超过大小上限 0.000976562 MB"}
    }
    assert stored_files(tmp_path / "storage") == []


def test_size_limit_only_applies_to_the_upload_route(client):
    resp = client.post("/api/auth/register", content=b"x" * (1200 * 1024))

    # 不是 413：别的路由不受上传上限影响（这里因为不是合法 JSON 而得到 422）
    assert resp.status_code == 422
