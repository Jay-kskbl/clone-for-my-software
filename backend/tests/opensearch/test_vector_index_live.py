"""T21 🧪：对着真实的 OpenSearch 验证图片向量索引（M10）。

需要一个带 k-NN 插件的 OpenSearch（官方完整发行版自带），并设置环境变量 TEST_OPENSEARCH_URL。
不设置时本文件的测试全部跳过，算“未运行”。每次运行使用独立的索引名前缀，结束时只删自己建的索引。

DEVPLAN 要求：过滤后只返回有权限的文档。另外验证精确检索的排序、覆盖写入、删除、模型隔离。
"""

import math
import os
import uuid

import pytest
from shared.text_index import IMAGE_VECTORS, OpenSearchClient

from app.modules.vector_index import (
    VECTOR_DIM,
    delete_document_vectors,
    ensure_vector_index,
    index_image_vector,
    search_vectors,
)

OPENSEARCH_URL = os.environ.get("TEST_OPENSEARCH_URL")

pytestmark = pytest.mark.skipif(
    not OPENSEARCH_URL, reason="未设置 TEST_OPENSEARCH_URL，需要真实 OpenSearch 的测试未运行"
)

MODEL = {"model_name": "ViT-B-16", "model_version": "cn_clip-1.6.0-5997ef32c50d"}


def direction(angle: float) -> list[float]:
    """单位向量：只在前两维上，与第一维的夹角为 angle（弧度）。相似度随夹角单调下降。"""
    vector = [0.0] * VECTOR_DIM
    vector[0], vector[1] = math.cos(angle), math.sin(angle)
    return vector


@pytest.fixture
def client():
    prefix = f"test_{uuid.uuid4().hex[:10]}_"
    with OpenSearchClient(OPENSEARCH_URL, timeout_seconds=30.0, index_prefix=prefix) as c:
        assert ensure_vector_index(c) is True
        try:
            yield c
        finally:
            c.request("DELETE", f"/{c.index_name(IMAGE_VECTORS)}", also_accept={404})


@pytest.fixture
def images(client):
    """五个文档，与查询向量的夹角依次增大：文档 0 最相似。"""
    documents = [uuid.uuid4() for _ in range(5)]
    for rank, document_id in enumerate(documents):
        index_image_vector(
            client,
            image_id=str(document_id),
            document_id=document_id,
            sha256=f"{rank:064d}",
            vector=direction(rank * 0.3),
            **MODEL,
        )
    return documents


def search(client, document_ids, depth=10, **model):
    return search_vectors(
        client, direction(0.0), document_ids=document_ids, depth=depth, **{**MODEL, **model}
    )


def test_exact_search_ranks_by_similarity(client, images):
    hits = search(client, None)
    assert [h.document_id for h in hits] == images
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)
    # 不同 OpenSearch 版本对 cosinesimil 的绝对分数范围并不完全一致；
    # 这里验证真正依赖的性质：完全相同方向排第一，且分数严格递减。
    assert scores[0] > scores[1] > scores[2] > scores[3] > scores[4]


def test_filter_returns_only_accessible_documents(client, images):
    """🧪 过滤后只返回有权限的文档，且是在过滤后的集合里取前 k 个（不会因先取后滤而变少）。"""
    allowed = {images[3], images[4]}
    hits = search(client, allowed, depth=2)
    assert [h.document_id for h in hits] == [images[3], images[4]]
    # 最相似的三个文档都不在允许集合里；先取前 2 再过滤的话这里会是空的
    assert {h.document_id for h in search(client, allowed, depth=1)} == {images[3]}


def test_empty_accessible_set_returns_nothing(client, images):
    assert search(client, set()) == []


def test_unknown_document_ids_in_the_filter_are_harmless(client, images):
    hits = search(client, {uuid.uuid4(), images[2]})
    assert [h.document_id for h in hits] == [images[2]]


def test_vectors_of_another_model_are_not_compared(client, images):
    assert search(client, None, model_version="cn_clip-9.9.9-ffffffffffff") == []


def test_rewriting_an_image_overwrites_instead_of_adding(client, images):
    index_image_vector(
        client,
        image_id=str(images[4]),
        document_id=images[4],
        sha256="f" * 64,
        vector=direction(0.0),
        **MODEL,
    )
    hits = search(client, None)
    assert len(hits) == 5
    assert hits[0].document_id in {images[0], images[4]}


def test_deleted_document_is_no_longer_found(client, images):
    assert delete_document_vectors(client, images[0]) == 1
    assert images[0] not in {h.document_id for h in search(client, None)}
    assert delete_document_vectors(client, images[0]) == 0


def test_search_before_any_vector_creates_the_index(client):
    client.request("DELETE", f"/{client.index_name(IMAGE_VECTORS)}")
    assert search(client, None) == []
    assert client.request("HEAD", f"/{client.index_name(IMAGE_VECTORS)}").status_code == 200
