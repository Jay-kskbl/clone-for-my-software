"""M11：两个文本类通道对 OpenSearch 的查询。

    meta：doc_meta 索引，文件名与标签（B0）
    text：chunks 索引的 BM25，按 source_type 过滤（B1 只查 body，B2 查 body + ocr）

两个通道的输出都已经聚合到文件级：每个文档最多一条，按 BM25 分数从高到低。
chunks 索引用 OpenSearch 的 collapse 按 document_id 折叠，每个文档只留得分最高的片段，
它同时就是这个文档的命中证据（GLOBAL §4.2）。

权限：普通用户的查询带上“可访问的 document_id 集合”作为前置过滤，避免前 N 名被
别人的文档占满、过滤后结果变少。这只是为了召回，不是权限保证——保证是返回前的
数据库二次校验（附录 A10，见 service.py）。管理员可以访问全部文档，不加这个过滤。
"""

import html
import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Any

from shared.contracts import Evidence, SourceType

from app.modules.text_index import (
    CHUNKS,
    DOC_META,
    OpenSearchClient,
    TextIndexError,
    TextIndexUnavailable,
    ensure_indices,
)

_INDEX_NOT_FOUND = "index_not_found_exception"
# 两个索引都是 1 个分片，同分时按 document_id 排序，结果完全确定
_SORT = ["_score", {"document_id": "asc"}]


@dataclass(frozen=True)
class ChannelHits:
    # 按名次排好的（document_id，原始分数）
    ranking: list[tuple[uuid.UUID, float]]
    # text 通道每个文档的最佳片段；meta 通道为空
    evidence: dict[uuid.UUID, Evidence]


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
    return response.json()["hits"]["hits"]


def _score(hit: dict[str, Any]) -> float:
    # 显式按 _score 排序时，分数在 sort 数组的第一项
    return float(hit["sort"][0])


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
    hits = _search(client, DOC_META, body)
    return ChannelHits(
        ranking=[(uuid.UUID(hit["_source"]["document_id"]), _score(hit)) for hit in hits],
        evidence={},
    )


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
        source = hit["_source"]
        document_id = uuid.UUID(source["document_id"])
        if document_id in evidence:
            # collapse 已经保证每个文档一条；这里只是防御，保留排在前面的那一条
            continue
        ranking.append((document_id, _score(hit)))
        fragments = hit.get("highlight", {}).get("text")
        snippet = fragments[0] if fragments else html.escape(source["text"][:snippet_chars])
        evidence[document_id] = Evidence(
            chunk_id=source["chunk_id"],
            snippet=snippet,
            source_type=source["source_type"],
            locator=source["locator"],
        )
    return ChannelHits(ranking=ranking, evidence=evidence)
