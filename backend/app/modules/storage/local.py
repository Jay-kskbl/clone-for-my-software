"""M3 存储抽象的本地文件系统实现。

写入分两步（GLOBAL §6.2）：
  stage()  把内容写进 {root}/.tmp/ 下的临时文件，同时计算 sha256、检查大小、按魔数识别类型；
  commit() 把临时文件原子地移动到正式路径 {root}/{yyyy}/{document_id}/{sha256}.{ext}。
M2 在两步之间写数据库记录；数据库失败时调用 discard()。put() 是两步连做的简便方法。

本模块不依赖 Web 框架、数据库和 app.config，可以单独测试。
"""

import hashlib
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from app.modules.storage.errors import (
    EmptyFileError,
    FileTooLargeError,
    InvalidStorageKeyError,
    StorageError,
    StoredFileNotFoundError,
    UnsupportedFileTypeError,
)
from app.modules.storage.filetype import SUPPORTED_TYPES, FileType, detect_file_type

# 这两个标志不是每个系统都有：O_NOFOLLOW 在 Windows 上不存在（那里只剩 _resolve_key 的检查），
# O_BINARY 只在 Windows 上存在且必须加上，否则文件会被当成文本读。
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_BINARY = getattr(os, "O_BINARY", 0)

_TMP_DIR_NAME = ".tmp"
_COPY_CHUNK_BYTES = 1024 * 1024

_UUID_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
# storage_key 只接受本模块自己生成的形状。白名单比“禁止 ../”可靠：
# 绝对路径、上级目录、反斜杠、空字节、多余的层级都匹配不上。
_KEY_RE = re.compile(
    rf"[0-9]{{4}}/{_UUID_PATTERN}/[0-9a-f]{{64}}\.(?:{'|'.join(t.ext for t in SUPPORTED_TYPES)})"
)
_TOKEN_RE = re.compile(r"[0-9a-f]{32}")


@dataclass(frozen=True)
class StoredFile:
    """已保存到正式路径的文件。"""

    storage_key: str
    sha256: str
    size: int
    mime_type: str  # 按魔数识别的真实类型


@dataclass(frozen=True)
class StagedFile:
    """已写入临时位置并通过校验、尚未移动到正式路径的文件。

    storage_key 在暂存时就确定，M2 可以先把它写进数据库，再 commit。
    """

    token: str
    storage_key: str
    sha256: str
    size: int
    mime_type: str


class LocalStorage:
    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        # 之后所有路径检查都以解析过符号链接的根目录为准
        self._root = root.resolve()
        self._tmp_dir = self._root / _TMP_DIR_NAME
        self._tmp_dir.mkdir(exist_ok=True)
        if self._tmp_dir.is_symlink():
            raise StorageError("存储根目录下的临时目录是符号链接，拒绝使用")

    # ---- 写入 ----

    def stage(
        self, stream: BinaryIO, *, document_id: uuid.UUID, max_size: int | None = None
    ) -> StagedFile:
        """把 stream 写入临时文件并校验。任何失败都会删掉临时文件再抛出。

        max_size 为字节数上限，None 表示不限制（上限值由 M2 从配置传入）。
        """
        token = uuid.uuid4().hex
        tmp_path = self._tmp_path(token)
        try:
            sha256, size = self._copy_to(stream, tmp_path, max_size)
            if size == 0:
                raise EmptyFileError("文件内容为空")
            file_type = detect_file_type(tmp_path)
            if file_type is None:
                raise UnsupportedFileTypeError("不支持的文件类型")
        except BaseException:
            # 包括 KeyboardInterrupt：进程只要还能执行到这里，就不留临时文件
            tmp_path.unlink(missing_ok=True)
            raise

        return StagedFile(
            token=token,
            storage_key=self._make_key(document_id, sha256, file_type),
            sha256=sha256,
            size=size,
            mime_type=file_type.mime_type,
        )

    def commit(self, staged: StagedFile) -> StoredFile:
        """把暂存文件移动到正式路径。失败时删掉临时文件再抛出。"""
        tmp_path = self._tmp_path(staged.token)
        try:
            final_path = self._resolve_key(staged.storage_key)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            # mkdir 之后再查一次：目录是刚创建的还是早已存在的符号链接，要以实际状态为准
            final_path = self._resolve_key(staged.storage_key)
            # 临时目录和正式目录在同一个文件系统上，replace 是原子的：
            # 正式路径上要么没有文件，要么是完整文件。
            os.replace(tmp_path, final_path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

        return StoredFile(
            storage_key=staged.storage_key,
            sha256=staged.sha256,
            size=staged.size,
            mime_type=staged.mime_type,
        )

    def discard(self, staged: StagedFile) -> None:
        """放弃一个暂存文件（例如数据库写入失败）。重复调用是安全的。"""
        self._tmp_path(staged.token).unlink(missing_ok=True)

    def put(
        self, stream: BinaryIO, *, document_id: uuid.UUID, max_size: int | None = None
    ) -> StoredFile:
        """暂存并立即提交。"""
        return self.commit(self.stage(stream, document_id=document_id, max_size=max_size))

    # ---- 读取与删除 ----

    def open(self, storage_key: str) -> BinaryIO:
        """以只读二进制方式打开文件。调用方负责关闭。"""
        path = self._resolve_key(storage_key)
        try:
            # O_NOFOLLOW：检查之后、打开之前文件被换成符号链接时，打开会失败而不是跟过去
            fd = os.open(path, os.O_RDONLY | _O_NOFOLLOW | _O_BINARY)
        except FileNotFoundError:
            raise StoredFileNotFoundError(storage_key) from None
        return os.fdopen(fd, "rb")

    def delete(self, storage_key: str) -> None:
        """删除文件。文件已不存在时什么也不做：清理任务重试时会重复调用（GLOBAL §3.3 幂等）。"""
        path = self._resolve_key(storage_key)
        path.unlink(missing_ok=True)
        # 顺手删掉变空的 {document_id}/ 和 {yyyy}/ 目录；非空或已不存在时 rmdir 失败，属于正常情况
        for directory in (path.parent, path.parent.parent):
            try:
                directory.rmdir()
            except OSError:
                break

    # ---- 内部 ----

    def _tmp_path(self, token: str) -> Path:
        if not _TOKEN_RE.fullmatch(token):
            raise InvalidStorageKeyError("暂存标识不合法")
        return self._tmp_dir / f"{token}.part"

    @staticmethod
    def _make_key(document_id: uuid.UUID, sha256: str, file_type: FileType) -> str:
        year = datetime.now(UTC).year
        return f"{year:04d}/{document_id}/{sha256}.{file_type.ext}"

    def _resolve_key(self, storage_key: str) -> Path:
        """storage_key → 根目录内的绝对路径。不合法或会逃出根目录时抛 InvalidStorageKeyError。"""
        if not isinstance(storage_key, str) or not _KEY_RE.fullmatch(storage_key):
            raise InvalidStorageKeyError("storage_key 格式不合法")

        path = self._root / storage_key
        # 格式检查挡住了 ../ 和绝对路径，这里挡符号链接：
        # 中间目录若是符号链接，解析后的父目录就不等于按字面拼出来的父目录。
        if path.parent.resolve() != path.parent or path.is_symlink():
            raise InvalidStorageKeyError("storage_key 指向存储根目录之外")
        return path

    @staticmethod
    def _copy_to(stream: BinaryIO, dest: Path, max_size: int | None) -> tuple[str, int]:
        digest = hashlib.sha256()
        size = 0
        # "xb"：文件名是随机的，已存在就说明出了问题，不覆盖
        with dest.open("xb") as out:
            while chunk := stream.read(_COPY_CHUNK_BYTES):
                size += len(chunk)
                if max_size is not None and size > max_size:
                    raise FileTooLargeError(max_size)
                digest.update(chunk)
                out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        return digest.hexdigest(), size
