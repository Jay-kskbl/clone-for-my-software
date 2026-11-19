"""M11：三个检索通道。

    meta：doc_meta 索引，文件名与标签（B0）
    text：chunks 索引的 BM25，按 source_type 过滤（B1 只查 body，B2 查 body + ocr）
    image：CLIP 服务编码查询文本 → image_vectors 索引精确检索（B3，T22）

三个通道的输出都已经聚合到文件级：每个文档最多一条，按各自的原始分数从高到低。
chunks 索引用 OpenSearch 的 collapse 按 document_id 折叠，每个文档只留得分最高的片段，
它同时就是这个文档的命中证据（GLOBAL §4.2）。

权限：普通用户的查询带上“可访问的 document_id 集合”作为前置过滤，避免前 N 名被
别人的文档占满、过滤后结果变少。这只是为了召回，不是权限保证——保证是返回前的
数据库二次校验（附录 A10，见 service.py）。管理员可以访问全部文档，不加这个过滤。
"""

import html
import logging
import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from shared.contracts import Evidence, ImageLocator, SourceType
from shared.ids import parse_image_id
from shared.text_index import (
    CHUNKS,
    DOC_META,
    OpenSearchClient,
    TextIndexError,
    TextIndexUnavailable,
    ensure_indices,
)

from app.modules.clip import ClipClient, ClipError, ClipModel
from app.modules.vector_index import VECTOR_DIM, search_vectors

logger = logging.getLogger(__name__)

_INDEX_NOT_FOUND = "index_not_found_exception"
_BAD_RESPONSE = "检索服务返回了无法识别的应答"
# 两个索引都是 1 个分片，同分时按 document_id 排序，结果完全确定
_SORT = ["_score", {"document_id": "asc"}]


@dataclass(frozen=True)
class ChannelHits:
    # 按名次排好的（document_id，原始分数）
    ranking: list[tuple[uuid.UUID, float]]
    # text 通道每个文档的最佳片段；meta 通道为空
    evidence: dict[uuid.UUID, Evidence]


class ImageChannelUnavailable(Exception):
    """图像通道这一次没能执行。message 写给用户看，不含服务地址和查询内容。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class ImageHits:
    hits: ChannelHits
    # 编码查询文本的模型，随检索日志记录（GLOBAL §4.3）
    model: ClipModel


def _id_filter(document_ids: Collection[uuid.UUID] | None) -> list[dict[str, Any]]:
    if document_ids is None:
        return []
    return [{"terms": {"document_id": sorted(str(d) for d in document_ids)}}]


def _search(client: OpenSearchClient, logical_name: str, body: dict[str, Any]) -> list[dict]:
    """执行一次查询，返回 hits。

    索引还不存在（系统刚部署、还没有任何文档被解析过）时，按项目的 mapping 把索引建好
    再查一次——此时得到的空结果是真实的“没有数据”。不能直接把“索引不存在”当成空结果：
    那样会掩盖索引名前缀配错之类的故障。
    """
    path = f"/{client.index_name(logical_name)}/_search"
    try:
        response = client.request("POST", path, json=body)
    except TextIndexUnavailable:
        raise
    except TextIndexError as exc:
        if _INDEX_NOT_FOUND not in exc.message:
            raise
        ensure_indices(client)
        response = client.request("POST", path, json=body)
    # 状态码是 200 但内容不是预期的结构（例如中间的代理返回了别的东西）：这是检索服务的故障，
    # 要报成 503，不能让它变成一个没有说明的 500（GLOBAL §12）
    try:
        hits = response.json()["hits"]["hits"]
    except (ValueError, KeyError, TypeError) as exc:
        raise TextIndexUnavailable(_BAD_RESPONSE) from exc
    if not isinstance(hits, list):
        raise TextIndexUnavailable(_BAD_RESPONSE)
    return hits


def _document_id(hit: dict[str, Any]) -> uuid.UUID | None:
    """命中的 document_id；索引里的残留数据不是合法 UUID 时返回 None。

    这种数据不可能对应数据库里的文档，跳过即可（一致性检查会报告并清掉它，D31）；
    不能让一条坏数据使所有命中它的检索都失败。
    """
    try:
        return uuid.UUID(str(hit["_source"]["document_id"]))
    except (KeyError, TypeError, ValueError):
        logger.warning("检索结果里有 document_id 不合法的数据，已跳过（_id=%r）", hit.get("_id"))
        return None


def _score(hit: dict[str, Any]) -> float:
    # 显式按 _score 排序时，分数在 sort 数组的第一项
    try:
        return float(hit["sort"][0])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise TextIndexUnavailable(_BAD_RESPONSE) from exc


def search_meta(
    client: OpenSearchClient,
    query: str,
    *,
    document_ids: Collection[uuid.UUID] | None,
    depth: int,
    filename_weight: float,
    tags_weight: float,
) -> ChannelHits:
    """文件名与标签检索（B0）。"""
    if document_ids is not None and not document_ids:
        return ChannelHits(ranking=[], evidence={})
    body = {
        "size": depth,
        "track_total_hits": False,
        "_source": ["document_id"],
        "sort": _SORT,
        "query": {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": query,
                            "type": "best_fields",
                            "fields": [f"filename^{filename_weight}", f"tags^{tags_weight}"],
                        }
                    }
                ],
                "filter": _id_filter(document_ids),
            }
        },
    }
    ranking: list[tuple[uuid.UUID, float]] = []
    for hit in _search(client, DOC_META, body):
        document_id = _document_id(hit)
        if document_id is not None:
            ranking.append((document_id, _score(hit)))
    return ChannelHits(ranking=ranking, evidence={})


def search_text(
    client: OpenSearchClient,
    query: str,
    *,
    document_ids: Collection[uuid.UUID] | None,
    source_types: Sequence[SourceType],
    depth: int,
    snippet_chars: int,
) -> ChannelHits:
    """正文与 OCR 文字的 BM25 检索（B1、B2），每个文档取得分最高的片段。"""
    if document_ids is not None and not document_ids:
        return ChannelHits(ranking=[], evidence={})
    body = {
        "size": depth,
        "track_total_hits": False,
        "_source": ["chunk_id", "document_id", "source_type", "locator", "text"],
        "sort": _SORT,
        "query": {
            "bool": {
                "must": [{"match": {"text": {"query": query}}}],
                "filter": [
                    {"terms": {"source_type": sorted(set(source_types))}},
                    *_id_filter(document_ids),
                ],
            }
        },
        # 每个文档只保留得分最高的一个片段：文件级聚合（GLOBAL §4.2）
        "collapse": {"field": "document_id"},
        "highlight": {
            # encoder=html：片段原文先做 HTML 转义，再插入 <em>；
            # 前端可以把摘要当 HTML 显示，而文档里的 <script> 之类只会显示成文字
            "encoder": "html",
            "pre_tags": ["<em>"],
            "post_tags": ["</em>"],
            "fields": {
                "text": {
                    "fragment_size": snippet_chars,
                    "number_of_fragments": 1,
                    # 高亮器找不到可标记的词时（例如只靠词干匹配），从开头截一段
                    "no_match_size": snippet_chars,
                }
            },
        },
    }
    hits = _search(client, CHUNKS, body)

    ranking: list[tuple[uuid.UUID, float]] = []
    evidence: dict[uuid.UUID, Evidence] = {}
    for hit in hits:
        document_id = _document_id(hit)
        if document_id is None or document_id in evidence:
            # collapse 已经保证每个文档一条；这里只是防御，保留排在前面的那一条
            continue
        source = hit["_source"]
        fragments = (hit.get("highlight") or {}).get("text")
        try:
            snippet = fragments[0] if fragments else html.escape(source["text"][:snippet_chars])
            best = Evidence(
                chunk_id=source["chunk_id"],
                snippet=snippet,
                source_type=source["source_type"],
                locator=source["locator"],
            )
        except (KeyError, TypeError, ValidationError):
            # 片段不符合数据契约（不是本系统写入的数据）：同样跳过，不让整次检索失败
            logger.warning("检索结果里有不符合数据契约的片段，已跳过（_id=%r）", hit.get("_id"))
            continue
        ranking.append((document_id, _score(hit)))
        evidence[document_id] = best
    return ChannelHits(ranking=ranking, evidence=evidence)


def search_image(
    clip: ClipClient,
    client: OpenSearchClient,
    query: str,
    *,
    document_ids: Collection[uuid.UUID] | None,
    depth: int,
) -> ImageHits:
    """文本到图片的检索：查询文本 → CLIP 文本向量 → 精确检索最相似的图片。

    只和同一模型生成的图片向量比较（模型标识取自这次编码的应答）。
    任何故障都抛 ImageChannelUnavailable：图像通道是增强能力，它失败时由调用方降级为
    纯文本检索并标记（GLOBAL §12），而不是让整次检索失败，也不是当成“没有结果”。
    """
    try:
        encoded = clip.encode_text(query)
    except ClipError as exc:
        raise ImageChannelUnavailable(exc.message) from exc
    if encoded.model.dim != VECTOR_DIM:
        # 换了模型却没有改向量索引的 mapping 并重建：两边的向量不能比较
        raise ImageChannelUnavailable(
            f"CLIP 模型的向量维度（{encoded.model.dim}）与向量索引（{VECTOR_DIM}）不一致"
        )
    try:
        found = search_vectors(
            client,
            encoded.vector,
            document_ids=document_ids,
            model_name=encoded.model.model_name,
            model_version=encoded.model.model_version,
            depth=depth,
        )
    except TextIndexError as exc:
        raise ImageChannelUnavailable(f"向量索引检索失败：{exc.message}") from exc

    ranking: list[tuple[uuid.UUID, float]] = []
    evidence: dict[uuid.UUID, Evidence] = {}
    for hit in found:
        if hit.document_id in evidence:
            continue
        try:
            if parse_image_id(hit.image_id).document_id != hit.document_id:
                raise ValueError("image_id 不属于这个文档")
            best = Evidence(image_id=hit.image_id, locator=ImageLocator(image_id=hit.image_id))
        except (ValueError, ValidationError):
            logger.warning("向量检索结果里有不合法的 image_id，已跳过（%r）", hit.image_id)
            continue
        ranking.append((hit.document_id, hit.score))
        evidence[hit.document_id] = best
    return ImageHits(hits=ChannelHits(ranking=ranking, evidence=evidence), model=encoded.model)
