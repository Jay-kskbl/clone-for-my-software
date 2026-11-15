"""T15 🧪：检索接口在真实数据库上的行为。需要 TEST_DATABASE_URL，未设置时全部跳过。

OpenSearch 用假的网络层代替（替换 app.state.text_index），这样可以精确控制
“索引里有什么”，专门检验数据库这一侧的保证（附录 A10）：

- 删除后立即查不到；
- 取消共享后立即查不到；
- 同一文件不重复出现；
- 服务故障与“无结果”可以区分。

最后一部分另需 TEST_OPENSEARCH_URL，对着真实的 OpenSearch 跑一遍完整链路。
"""

import json
import os
import uuid

import httpx
import pytest
from shared.contracts import Chunk, PdfPageLocator
from shared.text_index import (
    INDEX_NAMES,
    OpenSearchClient,
    ensure_indices,
    index_doc_meta,
    index_document,
)
from sqlalchemy import func, select

from app.db.models import Document, DocumentShare, SearchLog, User
from app.modules.auth import create_user

PASSWORD = "correct-horse-battery"
VERSION = "c1-m500-o50-aaaaaaaaaaaa"


class FakeIndex:
    """按 document_id 预置“索引里的数据”。默认像 OpenSearch 一样执行 document_id 过滤；

    ignore_filters=True 时故意不过滤，模拟索引里有不该被看到的数据（残留、权限已变），
    用来证明挡住它们的是数据库二次校验。
    """

    def __init__(self) -> None:
        self.meta: list[uuid.UUID] = []
        self.text: list[uuid.UUID] = []
        self.ignore_filters = False
        self.requests: list[httpx.Request] = []

    def _allowed(self, body: dict) -> set[str] | None:
        for clause in body["query"]["bool"]["filter"]:
            if "document_id" in clause.get("terms", {}):
                return set(clause["terms"]["document_id"])
        return None

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "HEAD":
            return httpx.Response(200)
        body = json.loads(request.content)
        allowed = None if self.ignore_filters else self._allowed(body)
        is_meta = request.url.path.startswith("/doc_meta")
        hits = []
        for rank, document_id in enumerate(self.meta if is_meta else self.text):
            if allowed is not None and str(document_id) not in allowed:
                continue
            source = {"document_id": str(document_id)}
            if not is_meta:
                source.update(
                    chunk_id=f"{document_id}:{VERSION}:0",
                    source_type="body",
                    locator={"type": "pdf_page", "page": 3},
                    text="差旅报销标准",
                )
            hits.append({"_source": source, "sort": [10.0 - rank, str(document_id)]})
        return httpx.Response(200, json={"hits": {"hits": hits}})

    def client(self) -> OpenSearchClient:
        return OpenSearchClient(
            "http://search.test:9200",
            timeout_seconds=1.0,
            transport=httpx.MockTransport(self.handle),
        )


@pytest.fixture
def index(app) -> FakeIndex:
    fake = FakeIndex()
    app.state.text_index = fake.client()
    return fake


@pytest.fixture
def alice(session) -> User:
    return create_user(session, "alice", PASSWORD)


@pytest.fixture
def bob(session) -> User:
    return create_user(session, "bob", PASSWORD)


@pytest.fixture
def admin(session) -> User:
    return create_user(session, "root", PASSWORD, role="admin")


def login(client, username: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def add_document(session, owner: User, name: str = "报销制度.pdf") -> Document:
    document_id = uuid.uuid4()
    document = Document(
        id=document_id,
        owner_id=owner.id,
        filename=name,
        mime_type="application/pdf",
        size_bytes=1,
        sha256="0" * 64,
        storage_key=f"2026/{document_id}/{'0' * 64}.pdf",
        status="succeeded",
    )
    session.add(document)
    session.commit()
    return document


def search(client, headers, query: str = "报销", **extra):
    return client.post("/api/search", json={"query": query, **extra}, headers=headers)


def hit_ids(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [hit["document"]["id"] for hit in response.json()["hits"]]


# ---- 🧪 删除后立即查不到 ----


def test_deleted_document_disappears_from_search_immediately(client, session, index, alice):
    headers = login(client, "alice")
    document = add_document(session, alice)
    index.meta = index.text = [document.id]
    assert hit_ids(search(client, headers)) == [str(document.id)]

    assert client.delete(f"/api/documents/{document.id}", headers=headers).status_code == 204
    # 索引里仍然有它（清理任务还没跑），但检索结果里立刻没有了
    index.ignore_filters = True

    assert hit_ids(search(client, headers)) == []


def test_deleted_document_is_hidden_from_admin_too(client, session, index, alice, admin):
    document = add_document(session, alice)
    index.text = [document.id]
    client.delete(f"/api/documents/{document.id}", headers=login(client, "alice"))

    assert hit_ids(search(client, login(client, "root"))) == []


# ---- 🧪 取消共享后立即查不到 ----


def test_unsharing_removes_the_document_from_search_immediately(client, session, index, alice, bob):
    document = add_document(session, alice)
    index.text = [document.id]
    as_bob = login(client, "bob")
    assert hit_ids(search(client, as_bob)) == []

    session.add(DocumentShare(document_id=document.id, user_id=bob.id))
    session.commit()
    assert hit_ids(search(client, as_bob)) == [str(document.id)]

    session.delete(session.get(DocumentShare, (document.id, bob.id)))
    session.commit()
    index.ignore_filters = True

    assert hit_ids(search(client, as_bob)) == []


def test_other_peoples_documents_never_appear_even_if_the_index_leaks_them(
    client, session, index, alice, bob
):
    mine = add_document(session, bob, "我的.pdf")
    theirs = add_document(session, alice, "别人的.pdf")
    index.meta = index.text = [theirs.id, mine.id]
    index.ignore_filters = True

    assert hit_ids(search(client, login(client, "bob"))) == [str(mine.id)]


def test_permission_prefilter_is_sent_to_the_index(client, session, index, alice, bob):
    mine = add_document(session, bob)
    add_document(session, alice)

    search(client, login(client, "bob"))

    bodies = [json.loads(r.content) for r in index.requests if r.method == "POST"]
    assert len(bodies) == 2
    for body in bodies:
        assert {"terms": {"document_id": [str(mine.id)]}} in body["query"]["bool"]["filter"]


def test_admin_sees_everyone_s_documents(client, session, index, alice, bob, admin):
    a, b = add_document(session, alice), add_document(session, bob)
    index.text = [a.id, b.id]

    assert sorted(hit_ids(search(client, login(client, "root")))) == sorted([str(a.id), str(b.id)])


def test_document_whose_record_is_gone_is_dropped(client, session, index, alice):
    # 索引里的残留：记录已经被硬删除（decisions.md D27 的竞态）
    index.text = [uuid.uuid4()]
    index.ignore_filters = True

    assert hit_ids(search(client, login(client, "alice"))) == []


# ---- 🧪 同一文件不重复出现 ----


def test_document_hit_by_both_channels_appears_once_with_both_ranks(client, session, index, alice):
    document = add_document(session, alice)
    index.meta = index.text = [document.id]

    response = search(client, login(client, "alice"))

    (hit,) = response.json()["hits"]
    assert [c["channel"] for c in hit["channels"]] == ["meta", "text"]
    assert hit["evidence"]["chunk_id"] == f"{document.id}:{VERSION}:0"
    assert hit["evidence"]["locator"] == {"type": "pdf_page", "page": 3}
    assert hit["document"]["filename"] == "报销制度.pdf"


# ---- 🧪 服务故障与“无结果”可以区分 ----


def test_no_match_is_200_with_an_empty_list(client, session, index, alice):
    response = search(client, login(client, "alice"))

    assert response.status_code == 200
    body = response.json()
    assert body["hits"] == []
    assert {c["channel"]: c["status"] for c in body["channels"]} == {
        "meta": "ok",
        "text": "ok",
        "image": "disabled",
    }


def test_search_service_down_is_503_search_unavailable(client, session, alice):
    # 不替换 text_index：conftest 里的 OpenSearch 地址指向一个没有服务的端口
    add_document(session, alice)

    response = search(client, login(client, "alice"))

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SEARCH_UNAVAILABLE"
    assert "127.0.0.1" not in response.json()["error"]["message"]


# ---- 检索日志 ----


def test_every_search_is_logged_including_failures(client, session, alice):
    headers = login(client, "alice")

    search(client, headers, "第一次")  # 检索服务不可用 → 503

    session.expire_all()
    (log,) = session.scalars(select(SearchLog)).all()
    assert (log.user_id, log.query, log.results) == (alice.id, "第一次", [])
    assert log.channels["meta"]["status"] == "unavailable"
    assert log.config["params"]["rrf_k"] == 60


def test_successful_search_log_lists_the_results(client, session, index, alice):
    document = add_document(session, alice)
    index.text = [document.id]

    search(client, login(client, "alice"), "  报销 ", source_types=["body"])

    session.expire_all()
    (log,) = session.scalars(select(SearchLog)).all()
    assert log.query == "报销"
    assert log.config["source_types"] == ["body"]
    assert [r["document_id"] for r in log.results] == [str(document.id)]
    assert log.results[0]["channels"] == [{"channel": "text", "rank": 1, "score": 10.0}]
    assert log.channels["text"] == {
        "status": "ok",
        "took_ms": log.channels["text"]["took_ms"],
        "detail": None,
        "hits": 1,
    }


def test_invalid_request_is_not_logged(client, session, index, alice):
    response = search(client, login(client, "alice"), "   ")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert session.scalar(select(func.count()).select_from(SearchLog)) == 0


# ---- 接口层 ----


def test_search_requires_login(client, index):
    assert client.post("/api/search", json={"query": "报销"}).status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {"query": "报销", "unknown": 1},
        {"query": "报销", "channels": {"video": True}},
        {"query": "报销", "source_types": ["pdf"]},
        {"query": "报销", "channels": {"meta": False, "text": False}},
        {},
    ],
)
def test_malformed_requests_are_422(client, index, alice, body):
    response = client.post("/api/search", json=body, headers=login(client, "alice"))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ---- 真实 OpenSearch ----

OPENSEARCH_URL = os.environ.get("TEST_OPENSEARCH_URL")


@pytest.mark.skipif(not OPENSEARCH_URL, reason="未设置 TEST_OPENSEARCH_URL，未运行")
def test_full_text_search_against_a_real_index(app, client, session, alice):
    prefix = f"test_{uuid.uuid4().hex[:10]}_"
    real = OpenSearchClient(OPENSEARCH_URL, timeout_seconds=30.0, index_prefix=prefix)
    app.state.text_index = real
    try:
        ensure_indices(real)
        hit_doc, other = (
            add_document(session, alice, "差旅管理办法.pdf"),
            add_document(session, alice, "会议纪要.pdf"),
        )
        for document, text in ((hit_doc, "差旅报销标准按职级执行。"), (other, "会议安排。")):
            index_doc_meta(real, document_id=document.id, filename=document.filename, tags=[])
            index_document(
                real,
                document_id=document.id,
                parse_version=VERSION,
                chunks=[
                    Chunk.build(
                        document_id=document.id,
                        parse_version=VERSION,
                        seq=0,
                        source_type="body",
                        text=text,
                        locator=PdfPageLocator(page=1),
                    )
                ],
            )
        headers = login(client, "alice")

        response = search(client, headers, "报销标准")

        assert hit_ids(response) == [str(hit_doc.id)]
        snippet = response.json()["hits"][0]["evidence"]["snippet"]
        assert "<em>" in snippet
        # B0：只开文件名通道
        assert hit_ids(search(client, headers, "差旅", channels={"text": False})) == [
            str(hit_doc.id)
        ]
        # 删除后立即查不到
        client.delete(f"/api/documents/{hit_doc.id}", headers=headers)
        assert hit_ids(search(client, headers, "报销标准")) == []
    finally:
        for name in INDEX_NAMES:
            real.request("DELETE", f"/{real.index_name(name)}", also_accept={404})
        real.close()
