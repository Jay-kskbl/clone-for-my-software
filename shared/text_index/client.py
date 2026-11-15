"""M8：访问 OpenSearch 的薄封装。

直接用 httpx 调 REST 接口，不引入 opensearch-py：本模块只用到建索引、批量写入、
按条件删除这几个接口，没有必要为此多带一个客户端库。

这里只做三件事：统一超时、给索引名加前缀、把各种失败转换成本模块的两类错误。
不重试——重试由任务框架负责（附录 A3）。
"""

import re
from collections.abc import Collection, Mapping
from typing import Any

import httpx

from shared.text_index.errors import TextIndexError, TextIndexUnavailable

# 两个索引的逻辑名（附录 A8）。实际的索引名是“前缀 + 逻辑名”
DOC_META = "doc_meta"
CHUNKS = "chunks"
INDEX_NAMES = (DOC_META, CHUNKS)

# OpenSearch 的索引名只能是小写，且不能以 _ 或 - 开头
INDEX_PREFIX_PATTERN = r"^([a-z0-9][a-z0-9_-]*)?$"

_OK = frozenset({200, 201})
# 429：服务端忙不过来，稍后重试可能成功，与 5xx 归为一类
_TRY_LATER = frozenset({429})


def _error_summary(response: httpx.Response) -> str:
    """从错误应答里取出类型和原因，取不到就只报状态码。不包含服务地址。"""
    try:
        error = response.json().get("error")
    except (ValueError, AttributeError):
        return f"HTTP {response.status_code}"
    if isinstance(error, Mapping):
        return f"HTTP {response.status_code}，{error.get('type')}：{error.get('reason')}"
    return f"HTTP {response.status_code}"


class OpenSearchClient:
    """一个 OpenSearch 节点的连接。用完调用 close()，或者用 with。"""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float,
        index_prefix: str = "",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """index_prefix：加在索引名前面，让测试使用独立的索引、不碰正式数据。

        transport：只给测试用，用来替换真实的网络访问。
        """
        if not re.fullmatch(INDEX_PREFIX_PATTERN, index_prefix):
            raise ValueError(f"索引名前缀只能包含小写字母、数字、'_'、'-'：{index_prefix!r}")
        self._prefix = index_prefix
        self._http = httpx.Client(base_url=base_url, timeout=timeout_seconds, transport=transport)

    def __enter__(self) -> "OpenSearchClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def index_name(self, logical_name: str) -> str:
        if logical_name not in INDEX_NAMES:
            raise ValueError(f"未知的索引：{logical_name!r}")
        return f"{self._prefix}{logical_name}"

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json: Any = None,
        content: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        also_accept: Collection[int] = (),
    ) -> httpx.Response:
        """发一个请求。成功（200/201，或 also_accept 里列出的状态码）时返回应答。

        连不上、超时、5xx、429 → TextIndexUnavailable（可重试）；
        其余 4xx → TextIndexError（不可重试）。
        """
        try:
            response = self._http.request(
                method, path, params=params, json=json, content=content, headers=headers
            )
        except httpx.HTTPError as exc:
            # 不带上异常的文字：里面有服务的主机名和端口
            raise TextIndexUnavailable(f"检索服务连接失败（{type(exc).__name__}）") from exc

        status = response.status_code
        if status in _OK or status in also_accept:
            return response
        if status >= 500 or status in _TRY_LATER:
            raise TextIndexUnavailable(f"检索服务暂时不可用（{_error_summary(response)}）")
        raise TextIndexError(f"检索服务拒绝了请求（{_error_summary(response)}）")


def client_from_settings(settings: Any) -> OpenSearchClient:
    """按配置创建客户端。settings 是 app.config.Settings。"""
    return OpenSearchClient(
        settings.opensearch_url,
        timeout_seconds=settings.opensearch_timeout_seconds,
        index_prefix=settings.opensearch_index_prefix,
    )
