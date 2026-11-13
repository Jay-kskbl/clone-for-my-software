"""M3 存储抽象：字节流 → storage_key；按 key 读取、删除。"""

from app.modules.storage.errors import (
    EmptyFileError,
    FileTooLargeError,
    InvalidStorageKeyError,
    StorageError,
    StoredFileNotFoundError,
    UnsupportedFileTypeError,
)
from app.modules.storage.filetype import FileType, detect_file_type
from app.modules.storage.local import LocalStorage, StagedFile, StoredFile

__all__ = [
    "EmptyFileError",
    "FileTooLargeError",
    "FileType",
    "InvalidStorageKeyError",
    "LocalStorage",
    "StagedFile",
    "StorageError",
    "StoredFile",
    "StoredFileNotFoundError",
    "UnsupportedFileTypeError",
    "detect_file_type",
]
