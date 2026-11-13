"""M5 文档解析：文件路径 → ParsedDocument（纯函数）。"""

from app.modules.parsing.errors import ParseError
from app.modules.parsing.pdf import parse_pdf

__all__ = ["ParseError", "parse_pdf"]
