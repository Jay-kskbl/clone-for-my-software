"""M6 OCR 的输出。"""

from uuid import UUID

from pydantic import Field

from shared.contracts.base import Contract
from shared.contracts.locators import OcrLocator


class Point(Contract):
    x: float
    y: float


class OCRLine(Contract):
    text: str
    # 文本框的四个顶点（左上、右上、右下、左下），像素坐标。
    # 用四边形而不是矩形：倾斜的文字检测出来不是正矩形。
    bbox: tuple[Point, Point, Point, Point]
    confidence: float = Field(ge=0.0, le=1.0)


class OCRResult(Contract):
    document_id: UUID
    # 被识别的对象：PDF 的某一页，或一张图片
    locator: OcrLocator
    lines: list[OCRLine] = Field(default_factory=list)
    # 记录模型名称和版本，实验可复现需要（GLOBAL §3.1）
    model_name: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
