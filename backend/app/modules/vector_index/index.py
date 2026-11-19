"""image_vectors 索引：结构、写入、删除、精确检索。

索引里一条数据对应一张图片，_id 就是 image_id（独立上传的图片等于 document_id），
同一张图片写两次是覆盖，不是追加（附录 A7 的确定性 ID 思路）。

精确检索用 k-NN 插件的打分脚本（lang=knn、source=knn_score，space_type=cosinesimil），
这是 T00 环境实测（env_check/01_check_opensearch.py，2026-11-16 在 2.19.1 上通过）用的写法。
mapping 里不开 index.knn、不配置 method：不建近似检索用的图，只用暴力计算（附录 A12）。
"""

import json
import logging
import math
import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared.text_index import IMAGE_VECTORS, OpenSearchClient, TextIndexError, TextIndexUnavailable

logger = logging.getLogger(__name__)

_MAPPING_FILE = Path(__file__).parent / "mappings" / "image_vectors.json"
_ALREADY_EXISTS = "resource_already_exists_exception"
_INDEX_NOT_FOUND = "index_not_found_exception"
_BAD_RESPONSE = "检索服务返回了无法识别的应答"
# 同分时按 document_id 排序，结果完全确定（与文本通道相同）
_SORT = ["_score", {"document_id": "asc"}]


def load_vector_index_definition() -> dict[str, Any]:
    """读出 image_vectors 索引的 settings + mappings。"""
    return json.loads(_MAPPING_FILE.read_text(encoding="utf-8"))


# 向量维度以 mapping 为准，写入和检索前都核对；换模型要改 mapping 并重建索引
VECTOR_DIM: int = load_vector_index_definition()["mappings"]["properties"]["vector"]["dimension"]


@dataclass(frozen=True)
class VectorHit:
    """向量通道的一条命中，已按文档折叠（每个文档只留最相似的一张图片）。"""

    document_id: uuid.UUID
    image_id: str
    score: float


def _refresh(refresh: bool) -> dict[str, str]:
    return {"refresh": "true" if refresh else "false"}


def _check_vector(vector: Sequence[float]) -> list[float]:
    if len(vector) != VECTOR_DIM:
        raise ValueError(f"向量维度是 {len(vector)}，向量索引要求 {VECTOR_DIM}")
    values = [float(x) for x in vector]
    if not all(math.isfinite(x) for x in values):
        raise ValueError("向量里有非有限值")
    return values


def ensure_vector_index(client: OpenSearchClient) -> bool:
    """索引不存在就创建，已存在的不动（已建好的索引不会被改，改 mapping 后要重建）。

    返回这次是否新建。重复调用没有副作用。
    """
    index = client.index_name(IMAGE_VECTORS)
    if client.request("HEAD", f"/{index}", also_accept={404}).status_code != 404:
        return False
    try:
        client.request("PUT", f"/{index}", json=load_vector_index_definition())
    except TextIndexError as exc:
        # 两个进程同时创建：另一个抢先建好了。结果一样，不算错
        if _ALREADY_EXISTS in exc.message:
            return False
        raise
    return True


def index_image_vector(
    client: OpenSearchClient,
    *,
    image_id: str,
    document_id: uuid.UUID,
    sha256: str,
    model_name: str,
    model_version: str,
    vector: Sequence[float],
    refresh: bool = True,
) -> None:
    """写入（或覆盖）一张图片的向量。"""
    index = client.index_name(IMAGE_VECTORS)
    client.request(
        "PUT",
        f"/{index}/_doc/{image_id}",
        params=_refresh(refresh),
        json={
            "image_id": image_id,
            "document_id": str(document_id),
            "sha256": sha256,
            "model_name": model_name,
            "model_version": model_version,
            "vector": _check_vector(vector),
        },
    )


def delete_document_vectors(
    client: OpenSearchClient, document_id: uuid.UUID, *, refresh: bool = True
) -> int:
    """删除一个文档的全部图片向量，返回删掉的条数。索引不存在时什么也不做。"""
    index = client.index_name(IMAGE_VECTORS)
    response = client.request(
        "POST",
        f"/{index}/_delete_by_query",
        # conflicts=proceed：遇到正在被修改的数据时不中途放弃，删完其余的再报告
        params={**_refresh(refresh), "conflicts": "proceed"},
        json={"query": {"term": {"document_id": str(document_id)}}},
        also_accept={404},
    )
    if response.status_code == 404:
        return 0
    try:
        result = response.json()
    except ValueError as exc:
        raise TextIndexUnavailable(_BAD_RESPONSE) from exc
    if result.get("failures"):
        raise TextIndexUnavailable("检索服务删除向量时部分失败")
    if result.get("version_conflicts"):
        raise TextIndexUnavailable("检索服务删除向量时遇到并发修改，有数据未删除")
    return int(result.get("deleted", 0))


def _query_body(
    query_vector: list[float],
    *,
    document_ids: Collection[uuid.UUID] | None,
    model_name: str,
    model_version: str,
    depth: int,
) -> dict[str, Any]:
    # 只和同一个模型生成的向量比较：不同模型的向量不在同一个空间里
    filters: list[dict[str, Any]] = [
        {"term": {"model_name": model_name}},
        {"term": {"model_version": model_version}},
    ]
    if document_ids is not None:
        # 前置过滤（附录 A12）：先缩小到可访问的文档，再逐一计算相似度，
        # 不会出现“先取前 k 条再过滤，结果不足 k 条”
        filters.append({"terms": {"document_id": sorted(str(d) for d in document_ids)}})
    return {
        "size": depth,
        "_source": ["document_id", "image_id"],
        "query": {
            "script_score": {
                "query": {"bool": {"filter": filters}},
                "script": {
                    "lang": "knn",
                    "source": "knn_score",
                    "params": {
                        "field": "vector",
                        "query_value": query_vector,
                        "space_type": "cosinesimil",
                    },
                },
            }
        },
        "sort": _SORT,
        # 文档内嵌图片（P4）出现后，一个文档会有多张图片：只留最相似的一张作为证据
        "collapse": {"field": "document_id"},
    }


def _parse_hit(hit: Any) -> VectorHit | None:
    """一条命中 → VectorHit。索引里的残留数据不合法时记日志并跳过，不让整次检索失败。"""
    try:
        source = hit["_source"]
        document_id = uuid.UUID(str(source["document_id"]))
        image_id = str(source["image_id"])
    except (KeyError, TypeError, ValueError):
        logger.warning("向量检索结果里有不合法的数据，已跳过（_id=%r）", _hit_id(hit))
        return None
    try:
        # 显式按 _score 排序时，分数在 sort 数组的第一项
        score = float(hit["sort"][0])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise TextIndexUnavailable(_BAD_RESPONSE) from exc
    return VectorHit(document_id=document_id, image_id=image_id, score=score)


def _hit_id(hit: Any) -> Any:
    return hit.get("_id") if isinstance(hit, dict) else None


def search_vectors(
    client: OpenSearchClient,
    query_vector: Sequence[float],
    *,
    document_ids: Collection[uuid.UUID] | None,
    model_name: str,
    model_version: str,
    depth: int,
) -> list[VectorHit]:
    """精确检索与 query_vector 最相似的图片，按文档折叠，按分数从高到低返回至多 depth 个。

    document_ids：可访问的文档集合；None 表示不过滤（管理员），空集合直接返回空结果。
    分数是 knn_score 在 cosinesimil 下的值（1 + 余弦相似度），只用来排名，不跨通道比较。
    检索服务出错时抛 TextIndexUnavailable / TextIndexError，不把故障变成空结果（GLOBAL §12）。
    """
    if depth < 1:
        raise ValueError("depth 至少为 1")
    if document_ids is not None and not document_ids:
        return []
    body = _query_body(
        _check_vector(query_vector),
        document_ids=document_ids,
        model_name=model_name,
        model_version=model_version,
        depth=depth,
    )
    path = f"/{client.index_name(IMAGE_VECTORS)}/_search"
    try:
        response = client.request("POST", path, json=body)
    except TextIndexError as exc:
        if _INDEX_NOT_FOUND not in exc.message:
            raise
        # 还没有任何图片编码过：建好索引，本次就是没有结果
        ensure_vector_index(client)
        return []
    try:
        hits = response.json()["hits"]["hits"]
    except (ValueError, KeyError, TypeError) as exc:
        raise TextIndexUnavailable(_BAD_RESPONSE) from exc
    if not isinstance(hits, list):
        raise TextIndexUnavailable(_BAD_RESPONSE)
    return [parsed for parsed in map(_parse_hit, hits) if parsed is not None]
