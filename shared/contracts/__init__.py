"""模块之间唯一的数据交换格式（GLOBAL §3.5）。"""

from shared.contracts.chunk import Chunk, SourceType
from shared.contracts.locators import (
    DocxParaLocator,
    ImageLocator,
    OcrLocator,
    PdfPageLocator,
    SourceLocator,
    XlsxRangeLocator,
)
from shared.contracts.ocr import OCRLine, OCRResult, Point
from shared.contracts.parsing import ParsedDocument, TextBlock
from shared.contracts.search import Channel, ChannelResult, Evidence, SearchHit

__all__ = [
    "Channel",
    "ChannelResult",
    "Chunk",
    "DocxParaLocator",
    "Evidence",
    "ImageLocator",
    "OCRLine",
    "OCRResult",
    "OcrLocator",
    "ParsedDocument",
    "PdfPageLocator",
    "Point",
    "SearchHit",
    "SourceLocator",
    "SourceType",
    "TextBlock",
    "XlsxRangeLocator",
]
