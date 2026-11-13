"""来源定位：一个文本片段或命中证据在原始文件里的位置（GLOBAL §3.5，附录 A9）。

多态字段，用 type 区分四种形态。不同格式能提供的定位精度不同，如实表达，不伪造。
"""

from typing import Annotated, Literal

from pydantic import Field, field_validator

from shared.contracts.base import Contract
from shared.ids import parse_image_id


class PdfPageLocator(Contract):
    type: Literal["pdf_page"] = "pdf_page"
    page: int = Field(ge=1, description="页码，从 1 开始")


class DocxParaLocator(Contract):
    # python-docx 拿不到页码，所以 Word 只定位到段落，不提供 page 字段
    type: Literal["docx_para"] = "docx_para"
    para_index: int = Field(ge=0, description="段落序号，从 0 开始")


class XlsxRangeLocator(Contract):
    type: Literal["xlsx_range"] = "xlsx_range"
    sheet: str = Field(min_length=1, description="工作表名")
    range: str = Field(
        pattern=r"^[A-Z]{1,3}[1-9][0-9]*(:[A-Z]{1,3}[1-9][0-9]*)?$",
        description="单元格范围，如 A1 或 A1:C10",
    )


class ImageLocator(Contract):
    type: Literal["image"] = "image"
    image_id: str

    @field_validator("image_id")
    @classmethod
    def _check_image_id(cls, value: str) -> str:
        parse_image_id(value)
        return value


SourceLocator = Annotated[
    PdfPageLocator | DocxParaLocator | XlsxRangeLocator | ImageLocator,
    Field(discriminator="type"),
]

# 能送去 OCR 的只有 PDF 的某一页或一张图片
OcrLocator = Annotated[PdfPageLocator | ImageLocator, Field(discriminator="type")]
