"""检索接口的请求与响应结构（docs/api.md §7.1）。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from shared.contracts import Channel, ChannelResult, Evidence, SourceType

from app.modules.documents.schemas import DocumentOut


class ChannelSwitches(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: bool | None = None
    text: bool | None = None
    image: bool | None = None


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 长度上限来自配置，在 service 里检查
    query: str
    top_k: int | None = None
    channels: ChannelSwitches | None = None
    source_types: list[SourceType] | None = Field(default=None)


class SearchHitOut(BaseModel):
    document: DocumentOut
    score: float
    channels: list[ChannelResult]
    evidence: Evidence | None


class ChannelStatusOut(BaseModel):
    channel: Channel
    status: Literal["ok", "disabled", "unavailable"]
    took_ms: int
    detail: str | None


class SearchResponse(BaseModel):
    hits: list[SearchHitOut]
    channels: list[ChannelStatusOut]
    took_ms: int
