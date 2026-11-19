"""M11：检索参数。全部来自配置，每次检索随日志一起记录（GLOBAL §8.2）。"""

from dataclasses import asdict, dataclass
from typing import Any

from shared.contracts import Channel

CHANNELS: tuple[Channel, ...] = ("meta", "text", "image")


@dataclass(frozen=True)
class SearchParams:
    rrf_k: int
    # 每个通道最多取多少个文件参与融合
    channel_depth: int
    # meta 通道里文件名与标签两个字段的权重
    meta_filename_weight: float
    meta_tags_weight: float
    # 命中片段（高亮摘要）的长度，按字符计
    snippet_chars: int
    default_top_k: int
    max_top_k: int
    max_query_chars: int
    # 图像通道编码查询文本的超时（秒）
    image_timeout_seconds: float
    # 请求里没有指定时，各通道是否开启
    default_channels: dict[Channel, bool]

    def to_log(self) -> dict[str, Any]:
        return asdict(self)


def params_from_settings(settings: Any) -> SearchParams:
    """settings 是 app.config.Settings。"""
    return SearchParams(
        rrf_k=settings.search_rrf_k,
        channel_depth=settings.search_channel_depth,
        meta_filename_weight=settings.search_meta_filename_weight,
        meta_tags_weight=settings.search_meta_tags_weight,
        snippet_chars=settings.search_snippet_chars,
        default_top_k=settings.search_default_top_k,
        max_top_k=settings.search_max_top_k,
        max_query_chars=settings.search_max_query_chars,
        image_timeout_seconds=settings.search_image_timeout_seconds,
        default_channels={
            "meta": settings.search_channel_meta_enabled,
            "text": settings.search_channel_text_enabled,
            "image": settings.search_channel_image_enabled,
        },
    )
