"""M5 文档解析：文件路径 → ParsedDocument（纯函数）。"""

from app.modules.parsing.errors import ParseError
from app.modules.parsing.excel import parse_xlsx
from app.modules.parsing.image import ImageInfo, parse_image, read_image_info
from app.modules.parsing.pdf import parse_pdf
from app.modules.parsing.word import parse_docx

__all__ = [
    "ImageInfo",
    "ParseError",
    "parse_docx",
    "parse_image",
    "parse_pdf",
    "parse_xlsx",
    "read_image_info",
]
