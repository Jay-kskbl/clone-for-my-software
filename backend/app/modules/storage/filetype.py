"""按文件内容（魔数）识别真实类型。不看文件名、扩展名和客户端声明的 MIME（GLOBAL §6.7）。

只识别本系统能解析的五种类型。旧版 .doc / .xls（OLE 格式）不在范围内：
python-docx 和 openpyxl 都读不了它们。
"""

import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileType:
    ext: str  # 存储路径使用的扩展名，不带点
    mime_type: str


PDF = FileType("pdf", "application/pdf")
PNG = FileType("png", "image/png")
JPEG = FileType("jpg", "image/jpeg")
DOCX = FileType("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
XLSX = FileType("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

SUPPORTED_TYPES = (PDF, PNG, JPEG, DOCX, XLSX)

_ZIP_MAGIC = b"PK\x03\x04"
_CONTENT_TYPES_NAME = "[Content_Types].xml"
# [Content_Types].xml 正常只有几 KB。设上限是为了不被伪造的超大条目拖垮（zip 炸弹）。
_CONTENT_TYPES_MAX_BYTES = 1024 * 1024

# docx / xlsx 都是 zip，靠主部件的内容类型区分。
# 带宏的 .docm / .xlsm 和模板 .dotx / .xltx 的主部件类型不同，不会被当成 docx / xlsx。
_OOXML_MAIN_PARTS = (
    (b"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml", DOCX),
    (b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml", XLSX),
)


def detect_file_type(path: Path) -> FileType | None:
    """识别 path 指向的文件的类型；不是受支持的类型时返回 None。"""
    with path.open("rb") as f:
        head = f.read(8)

    if head.startswith(b"%PDF-"):
        return PDF
    if head == b"\x89PNG\r\n\x1a\n":
        return PNG
    if head.startswith(b"\xff\xd8\xff"):
        return JPEG
    if head.startswith(_ZIP_MAGIC):
        return _detect_ooxml(path)
    return None


def _detect_ooxml(path: Path) -> FileType | None:
    try:
        with zipfile.ZipFile(path) as zf:
            info = zf.getinfo(_CONTENT_TYPES_NAME)
            if info.file_size > _CONTENT_TYPES_MAX_BYTES:
                return None
            with zf.open(info) as part:
                # 条目头里的 file_size 可以伪造，所以读取本身也限长
                content_types = part.read(_CONTENT_TYPES_MAX_BYTES + 1)
    except (zipfile.BadZipFile, KeyError, OSError, RuntimeError, NotImplementedError, EOFError):
        # 损坏的 zip、没有 [Content_Types].xml、加密或不支持的压缩方式：都不是可解析的 Office 文档
        return None

    if len(content_types) > _CONTENT_TYPES_MAX_BYTES:
        return None
    matches = [ft for marker, ft in _OOXML_MAIN_PARTS if marker in content_types]
    return matches[0] if len(matches) == 1 else None
