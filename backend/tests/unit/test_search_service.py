"""T15/T22：检索编排。不需要数据库、OpenSearch 和 CLIP 服务。

OpenSearch 和 CLIP 服务都用假的网络层代替；“可访问的文档集合”“数据库二次校验”“写检索日志”三处
数据库访问替换成可控的假函数。它们在真实数据库上的行为见 tests/integration/test_search_db.py。
"""

import json
import uuid
from types import SimpleNamespace

import httpx
import pytest
from shared.contracts import Evidence
from shared.text_index import OpenSearchClient

from app.core.errors import RequestInvalidError, SearchUnavailableError
from app.modules.clip import ClipClient
from app.modules.search import SearchParams, SearchRequestData, params_from_settings, search
from app.modules.search import service as service_module

A = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000000")
B = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000000")
C = uuid.UUID("cccccccc-0000-4000-8000-000000000000")
VERSION = "c1-m500-o50-aaaaaaaaaaaa"

PARAMS = SearchParams(
    rrf_k=60,
    channel_depth=50,
    meta_filename_weight=2.0,
    meta_tags_weight=1.0,
    snippet_chars=100,
    default_top_k=10,
    max_top_k=20,
    max_query_chars=50,
    image_timeout_seconds=1.0,
    default_channels={"meta": True, "text": True, "image": False},
)

USER = SimpleNamespace(id=uuid.uuid4(), role="user")
ADMIN = SimpleNamespace(id=uuid.uuid4(), role="admin")


def meta_hit(document_id: uuid.UUID, score: float) -> dict:
    return {"_source": {"document_id": str(document_id)}, "sort": [score, str(document_id)]}


def text_hit(document_id: uuid.UUID, score: float, *, seq: int = 0, highlight=True) -> dict:
    hit = {
        "_source": {
            "chunk_id": f"{document_id}:{VERSION}:{seq}",
            "document_id": str(document_id),
            "source_type": "body",
            "locator": {"type": "pdf_page", "page": seq + 1},
            "text": "差旅<报销>标准按照公司规定执行，" * 10,
        },
        "sort": [score, str(document_id)],
    }
    if highlight:
        hit["highlight"] = {"text": ["差旅<em>报销</em>标准"]}
    return hit


def image_hit(document_id: uuid.UUID, score: float, *, image_id: str | None = None) -> dict:
    return {
        "_source": {"document_id": str(document_id), "image_id": image_id or str(document_id)},
        "sort": [score, str(document_id)],
    }


class FakeOpenSearch:
    def __init__(self) -> None:
        self.meta_hits: list[dict] = []
        self.text_hits: list[dict] = []
        self.image_hits: list[dict] = []
        self.requests: list[httpx.Request] = []
        # 路径 → 要返回的错误应答（或要抛出的异常）
        self.failures: dict[str, object] = {}
        self.missing_indices: set[str] = set()

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        failure = self.failures.get(path)
        if isinstance(failure, Exception):
            raise failure
        if isinstance(failure, httpx.Response):
            return failure
        index = path.strip("/").split("/")[0]
        if request.method == "HEAD":
            return httpx.Response(404 if index in self.missing_indices else 200)
        if request.method == "PUT":
            self.missing_indices.discard(index)
            return httpx.Response(200, json={})
        if index in self.missing_indices:
            return httpx.Response(
                404,
                json={"error": {"type": "index_not_found_exception", "reason": "no such index"}},
            )
        hits = {"doc_meta": self.meta_hits, "image_vectors": self.image_hits}.get(
            index, self.text_hits
        )
        return httpx.Response(200, json={"hits": {"hits": hits}})

    def client(self) -> OpenSearchClient:
        return OpenSearchClient(
            "http://search.internal:9200",
            timeout_seconds=1.0,
            transport=httpx.MockTransport(self.handle),
        )

    def bodies(self, index: str) -> list[dict]:
        return [
            json.loads(r.content)
            for r in self.requests
            if r.method == "POST" and r.url.path == f"/{index}/_search"
        ]


@pytest.fixture
def os_server() -> FakeOpenSearch:
    return FakeOpenSearch()


CLIP_MODEL = {"model_name": "ViT-B-16", "model_version": "cn_clip-1.6.0-5997ef32c50d"}


class FakeClip:
    """假的 CLIP 服务。reply：要返回的应答，或要抛出的异常（模拟超时、连不上）。"""

    def __init__(self) -> None:
        self.reply: object = None
        self.dim = 512
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if isinstance(self.reply, Exception):
            raise self.reply
        if isinstance(self.reply, httpx.Response):
            return self.reply
        vector = [1.0] + [0.0] * (self.dim - 1)
        return httpx.Response(200, json={**CLIP_MODEL, "dim": self.dim, "vectors": [vector]})

    def client(self) -> ClipClient:
        return ClipClient(
            "http://clip.internal:8001",
            timeout_seconds=1.0,
            transport=httpx.MockTransport(self.handle),
        )


@pytest.fixture
def clip() -> FakeClip:
    return FakeClip()


@pytest.fixture
def db(monkeypatch):
    """替换三处数据库访问。live：数据库里“未删除且有权访问”的文档；logs：写下的日志。"""
    state = SimpleNamespace(accessible={A, B, C}, live={A, B, C}, logs=[])

    def accessible_ids(session, user):
        return None if user.role == "admin" else set(state.accessible)

    def live_documents(session, user, ids):
        return {d: SimpleNamespace(id=d) for d in ids if d in state.live}

    def write_log(session, user, **kwargs):
        state.logs.append(kwargs)

    monkeypatch.setattr(service_module, "_accessible_ids", accessible_ids)
    monkeypatch.setattr(service_module, "_live_documents", live_documents)
    monkeypatch.setattr(service_module, "_write_log", write_log)
    return state


def run(os_server, user=USER, params=PARAMS, clip=None, **request):
    request.setdefault("query", "报销标准")
    return search(
        None,
        user,
        SearchRequestData(**request),
        client=os_server.client(),
        params=params,
        clip=clip.client() if clip is not None else None,
    )


def ids(outcome) -> list[uuid.UUID]:
    return [hit.document_id for hit in outcome.hits]


def statuses(outcome) -> dict[str, str]:
    return {r.channel: r.status for r in outcome.channels}


# ---- 融合与证据 ----


def test_both_channels_are_fused_by_rrf(os_server, db):
    os_server.meta_hits = [meta_hit(A, 5.0), meta_hit(B, 3.0)]
    os_server.text_hits = [text_hit(B, 12.0), text_hit(C, 9.0)]

    outcome = run(os_server)

    # B：meta 第 2 + text 第 1，分数最高
    assert ids(outcome) == [B, A, C]
    best = outcome.hits[0]
    assert best.score == pytest.approx(1 / 62 + 1 / 61)
    assert [(c.channel, c.rank, c.score) for c in best.channels] == [
        ("meta", 2, 3.0),
        ("text", 1, 12.0),
    ]
    assert statuses(outcome) == {"meta": "ok", "text": "ok", "image": "disabled"}


def test_text_hit_carries_its_best_chunk_as_evidence(os_server, db):
    os_server.text_hits = [text_hit(A, 9.0, seq=4)]

    (hit,) = run(os_server).hits

    assert hit.evidence == Evidence(
        chunk_id=f"{A}:{VERSION}:4",
        snippet="差旅<em>报销</em>标准",
        source_type="body",
        locator={"type": "pdf_page", "page": 5},
    )


def test_meta_only_hit_has_no_evidence(os_server, db):
    os_server.meta_hits = [meta_hit(A, 5.0)]

    (hit,) = run(os_server).hits

    assert hit.evidence is None


def test_snippet_falls_back_to_escaped_text_when_nothing_is_highlighted(os_server, db):
    os_server.text_hits = [text_hit(A, 9.0, highlight=False)]

    (hit,) = run(os_server).hits

    # 原文里的 < > 被转义，摘要可以安全地当 HTML 显示
    assert hit.evidence.snippet.startswith("差旅&lt;报销&gt;标准")
    assert "<" not in hit.evidence.snippet
    assert len(hit.evidence.snippet) >= 100


# ---- 发出去的查询 ----


def test_text_query_collapses_by_document_and_filters_by_permission(os_server, db):
    db.accessible = {B, A}

    run(os_server, source_types=["body"])

    (body,) = os_server.bodies("chunks")
    assert body["size"] == 50
    assert body["collapse"] == {"field": "document_id"}
    assert body["query"]["bool"]["must"] == [{"match": {"text": {"query": "报销标准"}}}]
    assert body["query"]["bool"]["filter"] == [
        {"terms": {"source_type": ["body"]}},
        {"terms": {"document_id": sorted([str(A), str(B)])}},
    ]
    highlight = body["highlight"]
    assert highlight["encoder"] == "html"
    assert highlight["fields"]["text"]["fragment_size"] == 100


def test_meta_query_uses_the_configured_field_weights(os_server, db):
    run(os_server)

    (body,) = os_server.bodies("doc_meta")
    multi_match = body["query"]["bool"]["must"][0]["multi_match"]
    assert multi_match["fields"] == ["filename^2.0", "tags^1.0"]
    assert multi_match["query"] == "报销标准"


def test_source_types_default_to_body_and_ocr(os_server, db):
    run(os_server)

    (body,) = os_server.bodies("chunks")
    assert body["query"]["bool"]["filter"][0] == {"terms": {"source_type": ["body", "ocr"]}}


def test_admin_queries_are_not_filtered_by_document_id(os_server, db):
    run(os_server, user=ADMIN)

    for index in ("doc_meta", "chunks"):
        (body,) = os_server.bodies(index)
        assert not any("document_id" in f.get("terms", {}) for f in body["query"]["bool"]["filter"])


def test_user_without_any_document_does_not_query_at_all(os_server, db):
    db.accessible = set()

    outcome = run(os_server)

    assert outcome.hits == []
    assert os_server.requests == []
    assert statuses(outcome)["text"] == "ok"


def test_disabled_channels_are_not_queried(os_server, db):
    outcome = run(os_server, channels={"meta": False})

    assert os_server.bodies("doc_meta") == []
    assert len(os_server.bodies("chunks")) == 1
    assert statuses(outcome) == {"meta": "disabled", "text": "ok", "image": "disabled"}


# ---- 数据库二次校验（附录 A10）----


def test_documents_failing_the_database_check_are_dropped(os_server, db):
    # 索引里还有 B（已删除、已取消共享，或记录已经不存在），数据库说它不该出现
    os_server.meta_hits = [meta_hit(B, 9.0), meta_hit(A, 5.0)]
    os_server.text_hits = [text_hit(B, 12.0)]
    db.live = {A}

    outcome = run(os_server)

    assert ids(outcome) == [A]
    assert set(outcome.documents) == {A}


def test_admin_results_are_still_checked_against_the_database(os_server, db):
    os_server.text_hits = [text_hit(A, 9.0), text_hit(B, 8.0)]
    db.live = {B}

    assert ids(run(os_server, user=ADMIN)) == [B]


def test_top_k_is_applied_after_the_database_check(os_server, db):
    os_server.text_hits = [text_hit(d, 10.0 - i) for i, d in enumerate([A, B, C])]
    db.live = {B, C}

    # 先过滤再截取：A 被挡掉后仍然返回 2 个
    assert ids(run(os_server, top_k=2)) == [B, C]


def test_each_document_appears_once(os_server, db):
    os_server.meta_hits = [meta_hit(A, 5.0)]
    os_server.text_hits = [text_hit(A, 9.0, seq=0), text_hit(A, 8.0, seq=1), text_hit(B, 1.0)]

    outcome = run(os_server)

    assert ids(outcome) == [A, B]
    assert outcome.hits[0].evidence.chunk_id.endswith(":0")


# ---- 故障与“没有结果”必须能区分（GLOBAL §12）----


def test_no_match_is_an_empty_result_not_an_error(os_server, db):
    outcome = run(os_server)

    assert outcome.hits == []
    assert statuses(outcome) == {"meta": "ok", "text": "ok", "image": "disabled"}
    assert len(db.logs) == 1


@pytest.mark.parametrize(
    "failure",
    [
        httpx.Response(503, json={"error": "unavailable"}),
        httpx.Response(400, json={"error": {"type": "parsing_exception", "reason": "bad"}}),
        httpx.ConnectError("refused to search.internal:9200"),
    ],
)
@pytest.mark.parametrize("failing", ["/doc_meta/_search", "/chunks/_search"])
def test_search_service_failure_is_503_never_an_empty_result(os_server, db, failure, failing):
    if isinstance(failure, httpx.ConnectError):
        failure.request = httpx.Request("POST", "http://x")
    os_server.failures[failing] = failure
    os_server.meta_hits = [meta_hit(A, 5.0)]

    with pytest.raises(SearchUnavailableError) as excinfo:
        run(os_server)

    assert excinfo.value.status_code == 503
    assert excinfo.value.code == "SEARCH_UNAVAILABLE"
    assert "search.internal" not in excinfo.value.message
    # 故障也写日志，并记下是哪个通道出的问题
    (log,) = db.logs
    assert log["hits"] == []
    failed = "meta" if failing.startswith("/doc_meta") else "text"
    assert {r.channel: r.status for r in log["reports"]}[failed] == "unavailable"


def test_missing_indices_are_created_and_the_result_is_a_real_empty(os_server, db):
    # 刚部署、还没有任何文档被解析过：索引还不存在
    os_server.missing_indices = {"doc_meta", "chunks"}

    outcome = run(os_server)

    assert outcome.hits == []
    assert ("PUT", "/doc_meta") in [(r.method, r.url.path) for r in os_server.requests]
    assert ("PUT", "/chunks") in [(r.method, r.url.path) for r in os_server.requests]


def test_log_failure_after_a_search_failure_still_reports_the_search_failure(
    os_server, db, monkeypatch
):
    def broken_log(session, user, **kwargs):
        raise RuntimeError("database is gone")

    monkeypatch.setattr(service_module, "_write_log", broken_log)
    os_server.failures["/chunks/_search"] = httpx.Response(503, json={})
    session = SimpleNamespace(rollback=lambda: None)

    with pytest.raises(SearchUnavailableError):
        search(
            session,
            USER,
            SearchRequestData(query="报销"),
            client=os_server.client(),
            params=PARAMS,
        )


# ---- 图像通道（T22）----


def image_report(outcome):
    return next(r for r in outcome.channels if r.channel == "image")


def test_image_channel_encodes_the_query_and_searches_vectors(os_server, db, clip):
    os_server.image_hits = [image_hit(B, 1.8), image_hit(C, 1.5)]

    outcome = run(os_server, clip=clip, channels={"meta": False, "text": False, "image": True})

    assert ids(outcome) == [B, C]
    assert (image_report(outcome).status, image_report(outcome).hits) == ("ok", 2)
    (request,) = clip.requests
    assert (request.method, request.url.path) == ("POST", "/encode/text")
    assert json.loads(request.content) == {"texts": ["报销标准"]}
    (body,) = os_server.bodies("image_vectors")
    filters = body["query"]["script_score"]["query"]["bool"]["filter"]
    # 只和同一模型的向量比较；普通用户带可访问集合作为前置过滤（附录 A12）
    assert {"term": {"model_name": "ViT-B-16"}} in filters
    assert {"term": {"model_version": CLIP_MODEL["model_version"]}} in filters
    assert {"terms": {"document_id": sorted(str(d) for d in (A, B, C))}} in filters
    assert body["size"] == PARAMS.channel_depth


def test_image_hit_carries_the_image_as_evidence(os_server, db, clip):
    os_server.image_hits = [image_hit(B, 1.8)]

    outcome = run(os_server, clip=clip, channels={"image": True})

    (hit,) = outcome.hits
    assert hit.evidence.image_id == str(B)
    assert hit.evidence.chunk_id is None
    assert hit.evidence.locator.model_dump() == {"type": "image", "image_id": str(B)}


def test_three_channels_are_fused_by_rrf_by_hand(os_server, db, clip):
    # meta: A；text: A, B；image: B, C
    os_server.meta_hits = [meta_hit(A, 5.0)]
    os_server.text_hits = [text_hit(A, 9.0), text_hit(B, 3.0)]
    os_server.image_hits = [image_hit(B, 1.9), image_hit(C, 1.7)]

    outcome = run(os_server, clip=clip, channels={"image": True})

    # 手算（k=60）：A = 1/61 + 1/61；B = 1/62 + 1/61；C = 1/62
    assert ids(outcome) == [A, B, C]
    scores = [hit.score for hit in outcome.hits]
    assert scores == pytest.approx([2 / 61, 1 / 62 + 1 / 61, 1 / 62])
    b = outcome.hits[1]
    assert [(c.channel, c.rank, c.score) for c in b.channels] == [
        ("image", 1, 1.9),
        ("text", 2, 3.0),
    ]


def test_text_evidence_wins_over_image_evidence(os_server, db, clip):
    os_server.text_hits = [text_hit(B, 3.0)]
    os_server.image_hits = [image_hit(B, 1.9)]

    (hit,) = run(os_server, clip=clip, channels={"image": True}).hits

    assert hit.evidence.chunk_id is not None
    assert hit.evidence.image_id is None


@pytest.mark.parametrize(
    "reply, detail",
    [
        (httpx.ConnectError("refused"), "连接失败"),
        (httpx.ReadTimeout("slow"), "连接失败（ReadTimeout）"),
        (httpx.Response(503, json={"error": {"code": "X", "message": "y"}}), "暂时不可用"),
        (httpx.Response(422, json={"error": {"code": "VALIDATION_ERROR"}}), "拒绝"),
        (httpx.Response(200, json={"oops": 1}), "无法识别"),
    ],
    ids=["关闭", "超时", "5xx", "拒绝", "应答不对"],
)
def test_clip_failure_degrades_to_text_and_is_marked(os_server, db, clip, reply, detail):
    clip.reply = reply
    os_server.text_hits = [text_hit(A, 9.0)]

    outcome = run(os_server, clip=clip, channels={"image": True})

    assert ids(outcome) == [A]
    assert statuses(outcome) == {"meta": "ok", "text": "ok", "image": "unavailable"}
    assert detail in image_report(outcome).detail
    # 错误信息里没有服务地址
    assert "clip.internal" not in image_report(outcome).detail
    assert os_server.bodies("image_vectors") == []
    (log,) = db.logs
    assert log["config"]["image_model"] is None


def test_model_dimension_mismatch_degrades(os_server, db, clip):
    clip.dim = 256
    os_server.text_hits = [text_hit(A, 9.0)]

    outcome = run(os_server, clip=clip, channels={"image": True})

    assert ids(outcome) == [A]
    assert image_report(outcome).status == "unavailable"
    assert "维度" in image_report(outcome).detail
    assert os_server.bodies("image_vectors") == []


def test_vector_index_failure_degrades_instead_of_503(os_server, db, clip):
    os_server.failures["/image_vectors/_search"] = httpx.Response(
        400, json={"error": {"type": "search_phase_execution_exception", "reason": "x"}}
    )
    os_server.text_hits = [text_hit(A, 9.0)]

    outcome = run(os_server, clip=clip, channels={"image": True})

    assert ids(outcome) == [A]
    assert image_report(outcome).status == "unavailable"
    assert "向量索引" in image_report(outcome).detail


def test_missing_vector_index_is_a_real_empty_not_a_failure(os_server, db, clip):
    os_server.missing_indices.add("image_vectors")

    outcome = run(os_server, clip=clip, channels={"meta": False, "text": False, "image": True})

    assert outcome.hits == []
    assert image_report(outcome).status == "ok"


def test_image_alone_unavailable_is_200_with_nothing_and_marked(os_server, db, clip):
    clip.reply = httpx.ConnectError("refused")

    outcome = run(os_server, clip=clip, channels={"meta": False, "text": False, "image": True})

    assert outcome.hits == []
    assert image_report(outcome).status == "unavailable"


def test_without_a_clip_client_the_image_channel_is_unavailable(os_server, db):
    os_server.text_hits = [text_hit(A, 9.0)]

    outcome = run(os_server, channels={"image": True})

    assert ids(outcome) == [A]
    assert image_report(outcome).detail == "没有配置 CLIP 服务"


def test_image_channel_off_by_default_does_not_call_clip(os_server, db, clip):
    outcome = run(os_server, clip=clip)

    assert clip.requests == []
    assert statuses(outcome)["image"] == "disabled"


def test_image_hits_also_pass_the_database_check(os_server, db, clip):
    os_server.image_hits = [image_hit(B, 1.9), image_hit(C, 1.7)]
    db.live = {C}

    outcome = run(os_server, clip=clip, channels={"image": True})

    assert ids(outcome) == [C]


def test_admin_image_query_is_not_filtered_by_document_id(os_server, db, clip):
    run(os_server, user=ADMIN, clip=clip, channels={"image": True})

    (body,) = os_server.bodies("image_vectors")
    filters = body["query"]["script_score"]["query"]["bool"]["filter"]
    assert not any("terms" in f for f in filters)


def test_user_without_documents_does_not_search_vectors(os_server, db, clip):
    db.accessible = set()

    outcome = run(os_server, clip=clip, channels={"image": True})

    assert outcome.hits == []
    assert os_server.bodies("image_vectors") == []


def test_invalid_image_id_in_the_index_is_skipped(os_server, db, clip):
    os_server.image_hits = [image_hit(B, 1.9, image_id=str(C)), image_hit(C, 1.7)]

    outcome = run(os_server, clip=clip, channels={"meta": False, "text": False, "image": True})

    assert ids(outcome) == [C]


def test_text_failure_is_still_503_with_the_image_channel_on(os_server, db, clip):
    os_server.failures["/chunks/_search"] = httpx.ConnectError("down")

    with pytest.raises(SearchUnavailableError):
        run(os_server, clip=clip, channels={"image": True})

    (log,) = db.logs
    assert log["reports"][2].channel == "image"
    assert log["reports"][2].status == "unavailable"


def test_log_records_the_clip_model_used(os_server, db, clip):
    os_server.image_hits = [image_hit(B, 1.9)]

    run(os_server, clip=clip, channels={"image": True})

    (log,) = db.logs
    assert log["config"]["image_model"] == {**CLIP_MODEL, "dim": 512}
    assert log["config"]["params"]["image_timeout_seconds"] == 1.0


# ---- 请求校验 ----


@pytest.mark.parametrize(
    "request_kwargs, message",
    [
        ({"query": ""}, "不能为空"),
        ({"query": "   "}, "不能为空"),
        ({"query": "长" * 51}, "不能超过"),
        ({"top_k": 0}, "top_k"),
        ({"top_k": 21}, "top_k"),
        ({"channels": {"meta": False, "text": False}}, "至少要开启"),
        ({"source_types": []}, "source_types"),
    ],
)
def test_invalid_requests_are_422_and_send_nothing(os_server, db, request_kwargs, message):
    with pytest.raises(RequestInvalidError, match=message):
        run(os_server, **request_kwargs)

    assert os_server.requests == []
    assert db.logs == []


def test_query_is_trimmed(os_server, db):
    run(os_server, query="  报销标准  ")

    (body,) = os_server.bodies("chunks")
    assert body["query"]["bool"]["must"][0]["match"]["text"]["query"] == "报销标准"


# ---- 检索日志 ----


def test_log_records_query_effective_config_channels_and_results(os_server, db):
    os_server.meta_hits = [meta_hit(A, 5.0)]
    os_server.text_hits = [text_hit(A, 9.0)]

    run(os_server, query="  报销标准 ", top_k=5, source_types=["ocr", "body", "ocr"])

    (log,) = db.logs
    assert log["query"] == "报销标准"
    assert log["config"]["top_k"] == 5
    assert log["config"]["channels"] == {"meta": True, "text": True, "image": False}
    assert log["config"]["source_types"] == ["body", "ocr"]
    assert log["config"]["params"]["rrf_k"] == 60
    assert log["config"]["params"]["channel_depth"] == 50
    assert [hit.document_id for hit in log["hits"]] == [A]
    assert log["latency_ms"] >= 0


def test_params_come_from_settings():
    settings = SimpleNamespace(
        search_rrf_k=30,
        search_channel_depth=200,
        search_meta_filename_weight=1.5,
        search_meta_tags_weight=0.5,
        search_snippet_chars=80,
        search_default_top_k=10,
        search_max_top_k=50,
        search_max_query_chars=100,
        search_image_timeout_seconds=2.5,
        search_channel_meta_enabled=True,
        search_channel_text_enabled=False,
        search_channel_image_enabled=False,
    )

    params = params_from_settings(settings)

    assert (params.rrf_k, params.channel_depth, params.max_top_k) == (30, 200, 50)
    assert params.default_channels == {"meta": True, "text": False, "image": False}
    assert params.image_timeout_seconds == 2.5


# ---- 应答不符合预期时（Fable 5.2 复核补充）----


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>gateway</html>"),
        httpx.Response(200, json={"took": 1}),
        httpx.Response(200, json={"hits": {"hits": None}}),
        httpx.Response(200, json={"hits": {"hits": [{"_source": {"document_id": str(A)}}]}}),
    ],
    ids=["不是 JSON", "没有 hits", "hits 不是列表", "命中里没有排序值"],
)
def test_unrecognizable_response_is_503_not_a_crash(os_server, db, response):
    """状态码 200 但内容不对：这是检索服务的故障，要报 503，不能变成没有说明的 500。"""
    os_server.failures["/doc_meta/_search"] = response

    with pytest.raises(SearchUnavailableError):
        run(os_server, query="报销")
    report = next(r for r in db.logs[-1]["reports"] if r.channel == "meta")
    assert report.status == "unavailable"


def test_index_residue_with_an_invalid_document_id_is_skipped(os_server, db):
    """索引里的残留数据（document_id 不是合法 UUID）不能让命中它的检索全部失败。"""
    broken = {"_id": "x", "_source": {"document_id": "not-a-uuid"}, "sort": [9.0, "not-a-uuid"]}
    os_server.meta_hits = [broken, meta_hit(A, 3.0)]
    os_server.text_hits = [
        {**broken, "_source": {**text_hit(B, 1.0)["_source"], "document_id": "not-a-uuid"}},
        text_hit(A, 2.0),
    ]

    outcome = run(os_server, query="报销")

    assert ids(outcome) == [A]
    # 坏数据不占名次
    assert [c.rank for c in outcome.hits[0].channels] == [1, 1]


def test_chunk_violating_the_contract_is_skipped(os_server, db):
    bad = text_hit(B, 5.0)
    bad["_source"]["locator"] = {"type": "nonsense"}
    os_server.text_hits = [bad, text_hit(A, 2.0)]

    outcome = run(os_server, query="报销", channels={"meta": False})

    assert ids(outcome) == [A]
