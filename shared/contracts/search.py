"""M11 检索编排的输出。检索单位是 document_id（文件级，附录 A6）。"""

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from shared.contracts.base import Contract
from shared.contracts.chunk import SourceType
from shared.contracts.locators import SourceLocator

# meta：doc_meta 索引（文件名、标签，B0）；text：chunks 索引的 BM25；image：CLIP 向量检索
Channel = Literal["meta", "text", "image"]


class ChannelResult(Contract):
    """某个通道对一个文档给出的原始排名和分数（已聚合到文件级）。"""

    channel: Channel
    rank: int = Field(ge=1, description="该通道内的文件级排名，从 1 开始")
    score: float = Field(description="该通道的原始分数；不同通道的分数不可直接比较")


class Evidence(Contract):
    """命中证据：最佳片段或图片，只用于展示和定位，不参与排序。"""

    chunk_id: str | None = None
    image_id: str | None = None
    snippet: str | None = None
    source_type: SourceType | None = None
    locator: SourceLocator

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "Evidence":
        if (self.chunk_id is None) == (self.image_id is None):
            raise ValueError("证据必须是片段或图片二者之一：chunk_id 与 image_id 恰好提供一个")
        return self


class SearchHit(Contract):
    document_id: UUID
    score: float = Field(description="最终分数（融合后）")
    # 保留各通道的原始排名和分数，便于解释结果和做实验分析（GLOBAL §4.4）
    channels: list[ChannelResult] = Field(min_length=1)
    # 文件名通道命中时可能没有片段证据
    evidence: Evidence | None = None

    @model_validator(mode="after")
    def _channels_unique(self) -> "SearchHit":
        names = [c.channel for c in self.channels]
        if len(names) != len(set(names)):
            raise ValueError(f"同一通道不能出现两次：{names}")
        return self
