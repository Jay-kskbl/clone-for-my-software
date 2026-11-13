"""M5 文档解析的输出。"""

from pydantic import Field

from shared.contracts.base import Contract
from shared.contracts.locators import OcrLocator, SourceLocator


class TextBlock(Contract):
    text: str
    locator: SourceLocator


class ParsedDocument(Contract):
    """解析结果的统一结构。

    不含 document_id：解析器是"文件路径 → 结果"的纯函数，不需要知道文档 ID；
    document_id 在切分（M7）时由调用方传入。
    """

    parser_name: str = Field(min_length=1)
    parser_version: str = Field(min_length=1)
    blocks: list[TextBlock] = Field(default_factory=list)
    # 文本层不足、需要交给 OCR 的页或图片
    ocr_targets: list[OcrLocator] = Field(default_factory=list)
