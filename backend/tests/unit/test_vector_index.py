"""T21：图片向量索引（M10）。OpenSearch 用假的网络层代替，检查请求体和应答处理。

真实 OpenSearch 上的检索（🧪 过滤后只返回有权限的文档）见
tests/opensearch/test_vector_index_live.py。
"""

import json
import uuid

import httpx
import pytest
from shared.text_index import OpenSearchClient, TextIndexError, TextIndexUnavailable

from app.modules.vector_index import (
    VECTOR_DIM,
    VectorHit,
    delete_document_vectors,
    ensure_vector_index,
    index_image_vector,
    load_vector_index_definition,
    search_vectors,
)

DOC_A = uuid.UUID("00000000-0000-4000-8000-00000000000a")
DOC_B = uuid.UUID("00000000-0000-4000-8000-00000000000b")
MODEL = {"model_name": "ViT-B-16", "model_version": "cn_clip-1.6.0-5997ef32c50d"}


def unit_vector(position: int = 0) -> list[float]:
    vector = [0.0] * VECTOR_DIM
    vector[position] = 1.0
    return vector


class FakeOpenSearch:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.responses: dict[tuple[str, str], httpx.Response] = {}

    def reply(self, method: str, path: str, status: int, body=None) -> None:
        self.responses[(method, path)] = httpx.Response(
            status, json=body if body is not None else {}
        )

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responses.get((request.method, request.url.path), httpx.Response(200, json={}))

    def client(self, prefix: str = "") -> OpenSearchClient:
        return OpenSearchClient(
            "http://search.test:9200",
            timeout_seconds=1.0,
            index_prefix=prefix,
            transport=httpx.MockTransport(self.handle),
        )

    def body(self, index: int = -1) -> dict:
        return json.loads(self.requests[index].content)


@pytest.fixture
def fake() -> FakeOpenSearch:
    return FakeOpenSearch()


# ---- mapping ----


def test_mapping_is_exact_search_only_and_strict():
    definition = load_vector_index_definition()
    # 附录 A12：不开 index.knn、不配置 method，不建近似检索用的图
    assert "knn" not in definition["settings"]["index"]
    vector = definition["mappings"]["properties"]["vector"]
    assert vector == {"type": "knn_vector", "dimension": 512}
    assert VECTOR_DIM == 512
    assert definition["mappings"]["dynamic"] == "strict"
    # 权限信息不进索引（附录 A10）
    assert set(definition["mappings"]["properties"]) == {
        "image_id",
        "document_id",
        "sha256",
        "model_name",
        "model_version",
        "vector",
    }


def test_ensure_creates_the_index_with_prefix_only_when_missing(fake):
    fake.reply("HEAD", "/t_image_vectors", 404)
    assert ensure_vector_index(fake.client("t_")) is True
    assert [f"{r.method} {r.url.path}" for r in fake.requests] == [
        "HEAD /t_image_vectors",
        "PUT /t_image_vectors",
    ]
    assert fake.body() == load_vector_index_definition()

    fake.requests.clear()
    fake.reply("HEAD", "/t_image_vectors", 200)
    assert ensure_vector_index(fake.client("t_")) is False
    assert [r.method for r in fake.requests] == ["HEAD"]


def test_ensure_tolerates_a_concurrent_creation(fake):
    fake.reply("HEAD", "/image_vectors", 404)
    fake.reply(
        "PUT",
        "/image_vectors",
        400,
        {"error": {"type": "resource_already_exists_exception", "reason": "exists"}},
    )
    assert ensure_vector_index(fake.client()) is False


# ---- 写入与删除 ----


def test_index_image_vector_overwrites_by_image_id_and_refreshes(fake):
    index_image_vector(
        fake.client(),
        image_id=str(DOC_A),
        document_id=DOC_A,
        sha256="ab" * 32,
        vector=unit_vector(3),
        **MODEL,
    )
    (request,) = fake.requests
    assert (request.method, request.url.path) == ("PUT", f"/image_vectors/_doc/{DOC_A}")
    assert request.url.params["refresh"] == "true"
    body = fake.body()
    assert body == {
        "image_id": str(DOC_A),
        "document_id": str(DOC_A),
        "sha256": "ab" * 32,
        "vector": unit_vector(3),
        **MODEL,
    }


@pytest.mark.parametrize(
    "vector", [[1.0] * (VECTOR_DIM - 1), [1.0] * (VECTOR_DIM + 1), [float("nan")] * VECTOR_DIM]
)
def test_index_image_vector_rejects_wrong_dimension_or_non_finite(fake, vector):
    with pytest.raises(ValueError):
        index_image_vector(
            fake.client(),
            image_id="x",
            document_id=DOC_A,
            sha256="ab" * 32,
            vector=vector,
            **MODEL,
        )
    assert fake.requests == []


def test_delete_document_vectors_by_document_id(fake):
    fake.reply("POST", "/image_vectors/_delete_by_query", 200, {"deleted": 2})
    assert delete_document_vectors(fake.client(), DOC_A) == 2
    assert fake.body() == {"query": {"term": {"document_id": str(DOC_A)}}}
    assert fake.requests[0].url.params["conflicts"] == "proceed"


def test_delete_document_vectors_when_index_does_not_exist(fake):
    fake.reply("POST", "/image_vectors/_delete_by_query", 404, {"error": {"type": "x"}})
    assert delete_document_vectors(fake.client(), DOC_A) == 0


@pytest.mark.parametrize("body", [{"failures": [{"x": 1}]}, {"version_conflicts": 1}])
def test_partial_delete_is_retryable(fake, body):
    fake.reply("POST", "/image_vectors/_delete_by_query", 200, body)
    with pytest.raises(TextIndexUnavailable):
        delete_document_vectors(fake.client(), DOC_A)


# ---- 检索 ----


def hit(document_id, image_id, score):
    return {
        "_id": image_id,
        "_source": {"document_id": str(document_id), "image_id": image_id},
        "sort": [score, str(document_id)],
    }


def search(fake, document_ids, depth=10, **kwargs):
    return search_vectors(
        fake.client(),
        unit_vector(0),
        document_ids=document_ids,
        depth=depth,
        **{**MODEL, **kwargs},
    )


def test_search_body_is_exact_script_score_with_prefilter(fake):
    fake.reply(
        "POST",
        "/image_vectors/_search",
        200,
        {"hits": {"hits": [hit(DOC_B, str(DOC_B), 1.9), hit(DOC_A, str(DOC_A), 1.2)]}},
    )

    hits = search(fake, {DOC_B, DOC_A}, depth=7)

    assert hits == [
        VectorHit(document_id=DOC_B, image_id=str(DOC_B), score=1.9),
        VectorHit(document_id=DOC_A, image_id=str(DOC_A), score=1.2),
    ]
    body = fake.body()
    assert body["size"] == 7
    script_score = body["query"]["script_score"]
    # 过滤条件在 script_score.query 里：先过滤、再逐一计算（附录 A12）
    assert script_score["query"] == {
        "bool": {
            "filter": [
                {"term": {"model_name": MODEL["model_name"]}},
                {"term": {"model_version": MODEL["model_version"]}},
                {"terms": {"document_id": sorted([str(DOC_A), str(DOC_B)])}},
            ]
        }
    }
    assert script_score["script"]["lang"] == "knn"
    assert script_score["script"]["source"] == "knn_score"
    assert script_score["script"]["params"]["space_type"] == "cosinesimil"
    assert script_score["script"]["params"]["field"] == "vector"
    assert script_score["script"]["params"]["query_value"] == unit_vector(0)
    assert body["collapse"] == {"field": "document_id"}
    assert body["sort"] == ["_score", {"document_id": "asc"}]


def test_admin_search_has_no_document_filter(fake):
    fake.reply("POST", "/image_vectors/_search", 200, {"hits": {"hits": []}})
    assert search(fake, None) == []
    filters = fake.body()["query"]["script_score"]["query"]["bool"]["filter"]
    assert all("terms" not in f for f in filters)
    assert len(filters) == 2


def test_no_accessible_documents_means_no_request(fake):
    assert search(fake, set()) == []
    assert fake.requests == []


def test_missing_index_is_created_and_gives_no_results(fake):
    fake.reply(
        "POST",
        "/image_vectors/_search",
        404,
        {"error": {"type": "index_not_found_exception", "reason": "no such index"}},
    )
    fake.reply("HEAD", "/image_vectors", 404)

    assert search(fake, {DOC_A}) == []
    assert [f"{r.method} {r.url.path}" for r in fake.requests][-1] == "PUT /image_vectors"


def test_other_client_errors_are_not_turned_into_empty_results(fake):
    fake.reply(
        "POST",
        "/image_vectors/_search",
        400,
        {"error": {"type": "parsing_exception", "reason": "x"}},
    )
    with pytest.raises(TextIndexError):
        search(fake, {DOC_A})


def test_service_failure_is_raised_not_hidden(fake):
    fake.reply("POST", "/image_vectors/_search", 503, {})
    with pytest.raises(TextIndexUnavailable):
        search(fake, {DOC_A})


@pytest.mark.parametrize("body", [{}, {"hits": {}}, {"hits": {"hits": "x"}}])
def test_malformed_response_is_a_service_failure(fake, body):
    fake.reply("POST", "/image_vectors/_search", 200, body)
    with pytest.raises(TextIndexUnavailable):
        search(fake, {DOC_A})


def test_invalid_hits_are_skipped(fake):
    fake.reply(
        "POST",
        "/image_vectors/_search",
        200,
        {
            "hits": {
                "hits": [
                    {"_id": "bad", "_source": {"document_id": "not-a-uuid", "image_id": "bad"}},
                    {"_id": "nosource"},
                    hit(DOC_A, str(DOC_A), 1.5),
                ]
            }
        },
    )
    assert search(fake, {DOC_A}) == [VectorHit(DOC_A, str(DOC_A), 1.5)]


def test_query_vector_dimension_is_checked(fake):
    with pytest.raises(ValueError):
        search_vectors(fake.client(), [1.0, 0.0], document_ids={DOC_A}, depth=5, **MODEL)
    with pytest.raises(ValueError):
        search(fake, {DOC_A}, depth=0)
    assert fake.requests == []
