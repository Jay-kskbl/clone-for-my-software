"""CLIP 模型服务的 HTTP 客户端（httpx，带超时，附录 A5）。

错误分两类，供任务框架按 retryable 处理：
- ClipUnavailable（可重试）：连不上、超时、5xx、应答结构不对；
- ClipRejected（不可重试）：服务明确拒绝这张图片（413 太大、422 损坏或格式不支持）及其他 4xx。
不重试——重试由任务框架负责（附录 A3）。错误信息不含服务地址和输入内容。
"""

import math
from dataclasses import dataclass
from typing import Any

import httpx

# image_embeddings 的列宽（model_name varchar(128)，model_version varchar(64)）
_MAX_MODEL_NAME = 128
_MAX_MODEL_VERSION = 64
_BAD_RESPONSE = "CLIP 服务返回了无法识别的应答"


class ClipError(Exception):
    retryable = True

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ClipUnavailable(ClipError):
    """CLIP 服务暂时不可用，稍后重试可能成功。"""

    retryable = True


class ClipRejected(ClipError):
    """CLIP 服务拒绝了这个输入，重试也不会成功。"""

    retryable = False


@dataclass(frozen=True)
class ClipModel:
    """生成向量的模型标识，与 image_embeddings 的去重键对应（D10）。"""

    model_name: str
    model_version: str
    dim: int


@dataclass(frozen=True)
class EncodedImage:
    model: ClipModel
    vector: list[float]


def _error_summary(response: httpx.Response) -> str:
    try:
        error = response.json().get("error")
    except (ValueError, AttributeError):
        return f"HTTP {response.status_code}"
    if isinstance(error, dict) and isinstance(error.get("code"), str):
        message = error.get("message")
        if isinstance(message, str) and message:
            return f"HTTP {response.status_code}，{error['code']}：{message}"
        return f"HTTP {response.status_code}，{error['code']}"
    return f"HTTP {response.status_code}"


def _model_from(body: Any) -> ClipModel:
    try:
        name, version, dim = body["model_name"], body["model_version"], body["dim"]
    except (KeyError, TypeError) as exc:
        raise ClipUnavailable(_BAD_RESPONSE) from exc
    if (
        not isinstance(name, str)
        or not isinstance(version, str)
        or not 0 < len(name) <= _MAX_MODEL_NAME
        or not 0 < len(version) <= _MAX_MODEL_VERSION
        or isinstance(dim, bool)
        or not isinstance(dim, int)
        or dim < 1
    ):
        raise ClipUnavailable(_BAD_RESPONSE)
    return ClipModel(model_name=name, model_version=version, dim=dim)


def _vector_from(raw: Any, dim: int) -> list[float]:
    if not isinstance(raw, list) or len(raw) != dim:
        raise ClipUnavailable(_BAD_RESPONSE)
    try:
        vector = [float(x) for x in raw if not isinstance(x, bool)]
    except (TypeError, ValueError) as exc:
        raise ClipUnavailable(_BAD_RESPONSE) from exc
    if len(vector) != dim or not all(math.isfinite(x) for x in vector):
        raise ClipUnavailable(_BAD_RESPONSE)
    return vector


class ClipClient:
    """一个 CLIP 服务的连接。用完调用 close()，或者用 with。"""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """transport：只给测试用，用来替换真实的网络访问。"""
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=timeout_seconds, transport=transport
        )

    def __enter__(self) -> "ClipClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            # 不带上异常的文字：里面有服务的主机名和端口
            raise ClipUnavailable(f"CLIP 服务连接失败（{type(exc).__name__}）") from exc
        status = response.status_code
        if status == 200:
            try:
                return response.json()
            except ValueError as exc:
                raise ClipUnavailable(_BAD_RESPONSE) from exc
        if status >= 500 or status == 429:
            raise ClipUnavailable(f"CLIP 服务暂时不可用（{_error_summary(response)}）")
        raise ClipRejected(f"CLIP 服务拒绝了请求（{_error_summary(response)}）")

    def model(self) -> ClipModel:
        """当前加载的模型（GET /health）。服务在模型加载完之后才开始监听，能连上就代表可用。"""
        return _model_from(self._call("GET", "/health"))

    def encode_image(self, data: bytes) -> EncodedImage:
        """编码一张图片（POST /encode/image，请求体就是图片字节）。"""
        body = self._call(
            "POST",
            "/encode/image",
            content=data,
            headers={"Content-Type": "application/octet-stream"},
        )
        model = _model_from(body)
        return EncodedImage(model=model, vector=_vector_from(body.get("vector"), model.dim))


def clip_client_from_settings(settings: Any) -> ClipClient:
    """按配置创建客户端。settings 是 app.config.Settings。"""
    return ClipClient(
        settings.clip_service_url, timeout_seconds=settings.clip_encode_timeout_seconds
    )
