"""T14：LocalStorage.local_path —— 按 storage_key 取本地只读路径（解析库要的是路径）。"""

import io
import uuid

import pytest

from app.modules.storage import InvalidStorageKeyError, LocalStorage, StoredFileNotFoundError

PDF_BYTES = b"%PDF-1.7\nminimal content for the storage test\n"


@pytest.fixture
def storage(tmp_path) -> LocalStorage:
    return LocalStorage(tmp_path / "storage")


def test_local_path_points_at_the_stored_file(storage, tmp_path):
    stored = storage.put(io.BytesIO(PDF_BYTES), document_id=uuid.uuid4())

    path = storage.local_path(stored.storage_key)

    assert path.read_bytes() == PDF_BYTES
    assert path.is_absolute()
    # 路径在存储根目录之内
    assert (tmp_path / "storage").resolve() in path.resolve().parents


def test_local_path_of_a_deleted_file_raises_the_same_error_as_open(storage):
    stored = storage.put(io.BytesIO(PDF_BYTES), document_id=uuid.uuid4())
    storage.delete(stored.storage_key)

    with pytest.raises(StoredFileNotFoundError):
        storage.local_path(stored.storage_key)
    with pytest.raises(StoredFileNotFoundError):
        storage.open(stored.storage_key)


@pytest.mark.parametrize(
    "key",
    [
        "../../etc/passwd",
        "/etc/passwd",
        "2026/not-a-uuid/abc.pdf",
        "",
    ],
)
def test_local_path_rejects_keys_that_are_not_storage_keys(storage, key):
    with pytest.raises(InvalidStorageKeyError):
        storage.local_path(key)


def test_local_path_does_not_keep_the_file_open(storage):
    stored = storage.put(io.BytesIO(PDF_BYTES), document_id=uuid.uuid4())

    path = storage.local_path(stored.storage_key)

    # 取完路径后文件可以被正常删除（在 Windows 上，仍被打开的文件删不掉）
    storage.delete(stored.storage_key)
    assert not path.exists()
