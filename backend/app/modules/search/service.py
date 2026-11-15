"""M11：检索编排 v1（T15）。

顺序固定（GLOBAL §4.4、§4.5）：

    1. 校验请求，确定本次生效的通道和参数
    2. 各通道分别检索，各自已聚合到 document_id（channels.py）
    3. RRF 融合（rrf.py）
    4. 数据库二次校验：只保留未删除且当前用户有权访问的文档
    5. 截取前 top_k 个
    6. 写检索日志

第 4 步是“删除即时生效”“取消共享即时生效”的唯一保证（附录 A10），不得为了性能去掉。
它也挡住索引里的残留数据（例如记录已经不存在的文档，见 decisions.md D27）。

检索服务出错时抛 SearchUnavailableError（503），不返回空结果（GLOBAL §12）：
用户必须能区分“没有搜到”和“检索服务故障”。这种情况也写一条检索日志。

图像通道（CLIP）属于 T22，v1 还没有实现：请求开启它时，它的状态是 unavailable
并说明原因，其余通道照常执行。
"""

import logging
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from shared.contracts import Channel, Evidence, SearchHit, SourceType
from shared.text_index import OpenSearchClient, TextIndexError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import RequestInvalidError, SearchUnavailableError
from app.db.models import Document, SearchLog, User
from app.modules.auth.permissions import ADMIN_ROLE, accessible_document_ids, accessible_filter
from app.modules.search import channels as channel_queries
from app.modules.search.params import CHANNELS, SearchParams
from app.modules.search.rrf import fuse

logger = logging.getLogger(__name__)

ChannelState = Literal["ok", "disabled", "unavailable"]
SOURCE_TYPES: tuple[SourceType, ...] = ("body", "ocr")

_IMAGE_NOT_IMPLEMENTED = "图像检索尚未实现"
_UNAVAILABLE_MESSAGE = "检索服务暂时不可用，请稍后重试"


@dataclass(frozen=True)
class SearchRequestData:
    """检索请求。None 表示使用配置中的默认值。"""

    query: str
    top_k: int | None = None
    channels: dict[Channel, bool | None] = field(default_factory=dict)
    source_types: Sequence[SourceType] | None = None


@dataclass
class ChannelReport:
    channel: Channel
    status: ChannelState
    took_ms: int = 0
    detail: str | None = None
    hits: int = 0


@dataclass(frozen=True)
class SearchOutcome:
    hits: list[SearchHit]
    # hits 里每个文档的数据库记录，供接口层组装响应
    documents: dict[uuid.UUID, Document]
    channels: list[ChannelReport]
    took_ms: int


@dataclass(frozen=True)
class _Resolved:
    query: str
    top_k: int
    enabled: dict[Channel, bool]
    source_types: tuple[SourceType, ...]


def _resolve(request: SearchRequestData, params: SearchParams) -> _Resolved:
    query = request.query.strip()
    if not query:
        raise RequestInvalidError("检索词不能为空")
    if len(query) > params.max_query_chars:
        raise RequestInvalidError(f"检索词不能超过 {params.max_query_chars} 个字符")

    top_k = params.default_top_k if request.top_k is None else request.top_k
    if not 1 <= top_k <= params.max_top_k:
        raise RequestInvalidError(f"top_k 必须在 1 到 {params.max_top_k} 之间")

    enabled = {
        channel: params.default_channels[channel]
        if request.channels.get(channel) is None
        else bool(request.channels[channel])
        for channel in CHANNELS
    }
    if not any(enabled.values()):
        raise RequestInvalidError("至少要开启一个检索通道")

    if request.source_types is None:
        source_types = SOURCE_TYPES
    else:
        source_types = tuple(sorted(set(request.source_types)))
        if not source_types:
            raise RequestInvalidError("source_types 不能为空")
    return _Resolved(query=query, top_k=top_k, enabled=enabled, source_types=source_types)


def _accessible_ids(session: Session, user: User) -> set[uuid.UUID] | None:
    """前置过滤用的可访问文档集合；管理员返回 None，表示不加过滤。"""
    if user.role == ADMIN_ROLE:
        return None
    return accessible_document_ids(session, user)


def _live_documents(
    session: Session, user: User, document_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, Document]:
    """数据库二次校验：候选文档里未删除且当前用户有权访问的那些。每次都查，不缓存。"""
    if not document_ids:
        return {}
    rows = session.scalars(
        select(Document).where(Document.id.in_(document_ids), accessible_filter(user))
    )
    return {document.id: document for document in rows}


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _write_log(
    session: Session,
    user: User,
    *,
    query: str,
    config: dict[str, Any],
    reports: Sequence[ChannelReport],
    hits: Sequence[SearchHit],
    latency_ms: int,
) -> None:
    session.add(
        SearchLog(
            user_id=user.id,
            query=query,
            config=config,
            channels={
                r.channel: {
                    "status": r.status,
                    "took_ms": r.took_ms,
                    "detail": r.detail,
                    "hits": r.hits,
                }
                for r in reports
            },
            results=[
                {
                    "document_id": str(hit.document_id),
                    "score": hit.score,
                    "channels": [c.model_dump(mode="json") for c in hit.channels],
                    "evidence_chunk_id": hit.evidence.chunk_id if hit.evidence else None,
                }
                for hit in hits
            ],
            latency_ms=float(latency_ms),
        )
    )
    session.commit()


def search(
    session: Session,
    user: User,
    request: SearchRequestData,
    *,
    client: OpenSearchClient,
    params: SearchParams,
) -> SearchOutcome:
    started = time.perf_counter()
    resolved = _resolve(request, params)
    config = {
        "top_k": resolved.top_k,
        "channels": resolved.enabled,
        "source_types": list(resolved.source_types),
        "params": params.to_log(),
    }

    reports: dict[Channel, ChannelReport] = {
        channel: ChannelReport(channel=channel, status="disabled") for channel in CHANNELS
    }
    if resolved.enabled["image"]:
        reports["image"] = ChannelReport(
            channel="image", status="unavailable", detail=_IMAGE_NOT_IMPLEMENTED
        )

    allowed = _accessible_ids(session, user)
    rankings: dict[Channel, list[tuple[uuid.UUID, float]]] = {}
    evidence: dict[uuid.UUID, Evidence] = {}
    current: Channel | None = None
    try:
        if resolved.enabled["meta"]:
            current, channel_started = "meta", time.perf_counter()
            result = channel_queries.search_meta(
                client,
                resolved.query,
                document_ids=allowed,
                depth=params.channel_depth,
                filename_weight=params.meta_filename_weight,
                tags_weight=params.meta_tags_weight,
            )
            rankings["meta"] = result.ranking
            reports["meta"] = ChannelReport(
                "meta", "ok", _elapsed_ms(channel_started), hits=len(result.ranking)
            )
        if resolved.enabled["text"]:
            current, channel_started = "text", time.perf_counter()
            result = channel_queries.search_text(
                client,
                resolved.query,
                document_ids=allowed,
                source_types=resolved.source_types,
                depth=params.channel_depth,
                snippet_chars=params.snippet_chars,
            )
            rankings["text"] = result.ranking
            evidence = result.evidence
            reports["text"] = ChannelReport(
                "text", "ok", _elapsed_ms(channel_started), hits=len(result.ranking)
            )
    except TextIndexError as exc:
        # 两个文本类通道都依赖 OpenSearch：任何一个失败都说明检索服务有问题，整体报告故障，
        # 而不是悄悄只返回另一个通道的结果
        assert current is not None
        reports[current] = ChannelReport(
            current, "unavailable", _elapsed_ms(channel_started), detail=exc.message
        )
        logger.warning("检索失败：%s 通道（%s）", current, exc.message)
        try:
            _write_log(
                session,
                user,
                query=resolved.query,
                config=config,
                reports=list(reports.values()),
                hits=[],
                latency_ms=_elapsed_ms(started),
            )
        except Exception:  # noqa: BLE001 —— 日志写不进去不能掩盖原本的检索故障
            session.rollback()
            logger.exception("检索失败后写检索日志也失败了")
        raise SearchUnavailableError(_UNAVAILABLE_MESSAGE) from exc

    fused = fuse(rankings, k=params.rrf_k, depth=params.channel_depth)
    documents = _live_documents(session, user, [f.document_id for f in fused])

    hits: list[SearchHit] = []
    for item in fused:
        if item.document_id not in documents:
            continue
        hits.append(
            SearchHit(
                document_id=item.document_id,
                score=item.score,
                channels=list(item.channels),
                evidence=evidence.get(item.document_id),
            )
        )
        if len(hits) == resolved.top_k:
            break

    took_ms = _elapsed_ms(started)
    channel_reports = list(reports.values())
    _write_log(
        session,
        user,
        query=resolved.query,
        config=config,
        reports=channel_reports,
        hits=hits,
        latency_ms=took_ms,
    )
    return SearchOutcome(
        hits=hits,
        documents={hit.document_id: documents[hit.document_id] for hit in hits},
        channels=channel_reports,
        took_ms=took_ms,
    )
