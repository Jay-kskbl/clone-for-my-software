"""M11 检索编排：多通道检索、文件级聚合、RRF 融合、数据库二次校验、检索日志。"""

from app.modules.search.params import CHANNELS, SearchParams, params_from_settings
from app.modules.search.rrf import FusedDocument, fuse
from app.modules.search.service import (
    ChannelReport,
    SearchOutcome,
    SearchRequestData,
    search,
)

__all__ = [
    "CHANNELS",
    "ChannelReport",
    "FusedDocument",
    "SearchOutcome",
    "SearchParams",
    "SearchRequestData",
    "fuse",
    "params_from_settings",
    "search",
]
