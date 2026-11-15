"""storage_key → 存储根目录内的本地路径，并做安全检查（GLOBAL §3.5、§7.2）。

存储模块（backend，M3）和 OCR Worker（ocr 环境）共用这一份检查，不各写一套：
路径安全的规则只能有一处。

storage_key 的形状：{yyyy}/{document_id}/{sha256}.{ext}，全部由服务端生成。
"""

import re
from pathlib import Path

# 存储模块支持的扩展名。backend 的 storage/filetype.py 的 SUPPORTED_TYPES 必须与它一致
# （backend 有测试检查这一点）
STORAGE_EXTENSIONS = ("pdf", "png", "jpg", "docx", "xlsx")

_UUID_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
# 只接受服务端自己生成的形状。白名单比“禁止 ../”可靠：
# 绝对路径、上级目录、反斜杠、空字节、多余的层级都匹配不上。
KEY_RE = re.compile(
    rf"[0-9]{{4}}/{_UUID_PATTERN}/[0-9a-f]{{64}}\.(?:{'|'.join(STORAGE_EXTENSIONS)})"
)


class InvalidStorageKeyError(ValueError):
    """storage_key 格式不合法，或解析后的路径不在存储根目录内（路径穿越、符号链接）。"""


def resolve_storage_key(root: Path, storage_key: str) -> Path:
    """storage_key → root 内的绝对路径。不检查文件是否存在。

    root 应当是已经 resolve() 过的绝对路径；这里也会再 resolve 一次，保证比较可靠。
    """
    if not isinstance(storage_key, str) or not KEY_RE.fullmatch(storage_key):
        raise InvalidStorageKeyError("storage_key 格式不合法")

    path = root.resolve() / storage_key
    # 格式检查挡住了 ../ 和绝对路径，这里挡符号链接：
    # 中间目录若是符号链接，解析后的父目录就不等于按字面拼出来的父目录。
    if path.parent.resolve() != path.parent or path.is_symlink():
        raise InvalidStorageKeyError("storage_key 指向存储根目录之外")
    return path
