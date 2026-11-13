"""M3 存储模块的错误类型。M2 负责把它们转换成 HTTP 错误响应（docs/api.md §1）。"""


class StorageError(Exception):
    """存储模块所有错误的基类。"""


class EmptyFileError(StorageError):
    """上传内容为空。"""


class FileTooLargeError(StorageError):
    """内容超过调用方给出的大小上限。"""

    def __init__(self, max_size: int) -> None:
        super().__init__(f"文件超过大小上限 {max_size} 字节")
        self.max_size = max_size


class UnsupportedFileTypeError(StorageError):
    """按魔数识别不出受支持的文件类型（与扩展名、MIME 无关）。"""


class InvalidStorageKeyError(StorageError):
    """storage_key 格式不合法，或解析后的路径不在存储根目录内（路径穿越、符号链接）。"""


class StoredFileNotFoundError(StorageError):
    """storage_key 合法，但对应的文件不存在。"""
