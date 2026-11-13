"""M7 切分的输出，也是写入 chunks 索引和 DocumentChunk 表的单位。"""

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from shared.contracts.base import Contract
from shared.contracts.locators import SourceLocator
from shared.ids import PARSE_VERSION_PATTERN, make_chunk_id

# body：文档自带的文本层；ocr：OCR 识别出的文字。B1 / B2 实验只靠这个字段过滤来区分。
SourceType = Literal["body", "ocr"]


class Chunk(Contract):
    chunk_id: str
    document_id: UUID
    parse_version: str = Field(pattern=PARSE_VERSION_PATTERN)
    seq: int = Field(ge=0)
    source_type: SourceType
    text: str = Field(min_length=1)
    locator: SourceLocator

    @model_validator(mode="after")
    def _chunk_id_matches_fields(self) -> "Chunk":
        expected = make_chunk_id(self.document_id, self.parse_version, self.seq)
        if self.chunk_id != expected:
            raise ValueError(
                f"chunk_id 与其余字段不一致：期望 {expected!r}，实际 {self.chunk_id!r}"
            )
        return self

    @classmethod
    def build(
        cls,
        *,
        document_id: UUID,
        parse_version: str,
        seq: int,
        source_type: SourceType,
        text: str,
        locator: SourceLocator,
    ) -> "Chunk":
        """按 ID 规则生成 chunk_id，调用方不用自己拼。"""
        return cls(
            chunk_id=make_chunk_id(document_id, parse_version, seq),
            document_id=document_id,
            parse_version=parse_version,
            seq=seq,
            source_type=source_type,
            text=text,
            locator=locator,
        )
