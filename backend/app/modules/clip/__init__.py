"""调用 CLIP 模型服务（M9，services/clip_service）的客户端。

接口见 docs/api.md §9。T21 的 embed 任务用它编码图片；T22 的图像检索通道会在这里加文本编码。
"""

from app.modules.clip.client import (
    ClipClient,
    ClipError,
    ClipModel,
    ClipRejected,
    ClipUnavailable,
    EncodedImage,
    EncodedText,
    clip_client_from_settings,
    query_clip_client_from_settings,
)

__all__ = [
    "ClipClient",
    "ClipError",
    "ClipModel",
    "ClipRejected",
    "ClipUnavailable",
    "EncodedImage",
    "EncodedText",
    "clip_client_from_settings",
    "query_clip_client_from_settings",
]
