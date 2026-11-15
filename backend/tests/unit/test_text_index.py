"""T13：文本索引（M8）。本文件不需要 OpenSearch：用假的网络层接住请求，

检查发出去的请求对不对、各种应答是否被正确处理。
“重复索引不产生重复数据”“删除后查不到”这两项 🧪 只有真实的 OpenSearch 才能证明，
见 tests/opensearch/test_text_index_live.py。
"""

import json
import uuid

import httpx
import pytest
from shared.contracts import Chunk, DocxParaLocator, PdfPageLocator
from shared.text_index import (
    CHUNKS,
    DOC_META,
    OpenSearchClient,
    TextIndexError,
    TextIndexUnavailable,
    delete_document,
    ensure_indices,
    index_doc_meta,
    index_document,
    load_index_definition,
)
from shared.text_index import indexer as indexer_module

DOCUMENT_ID = uuid.UUID("11111111-2222-4333-8444-555555555555")
OTHER_DOCUMENT_ID = uuid.UUID("99999999-2222-4333-8444-555555555555")
VERSION = "c500o50-aaaaaaaaaaaa"
HOST = "search.internal.example"


class FakeOpenSearch:
    """记录收到的请求，并按预先设定的规则应答。"""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        # (方法, 路径) → 应答；没有设定的一律 200 + 空对象
        self.responses: dict[tuple[str, str], httpx.Response] = {}

    def reply(self, method: str, path: str, status: int, body: object = None) -> None:
        self.responses[(method, path)] = httpx.Response(
            status, json=body if body is not None else {}
        )

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responses.get((request.method, request.url.path), httpx.Response(200, json={}))

    def client(self, prefix: str = "") -> OpenSearchClient:
        return OpenSearchClient(
            f"http://{HOST}:9200",
            timeout_seconds=1.0,
            index_prefix=prefix,
            transport=httpx.MockTransport(self.handle),
        )

    def calls(self) -> list[tuple[str, str]]:
        return [(r.method, r.url.path) for r in self.requests]


@pytest.fixture
def server() -> FakeOpenSearch:
    return FakeOpenSearch()


def make_chunk(seq: int, text: str = "片段", *, document_id=DOCUMENT_ID, version=VERSION) -> Chunk:
    return Chunk.build(
        document_id=document_id,
        parse_version=version,
        seq=seq,
        source_type="body",
        text=f"{text}{seq}",
        locator=PdfPageLocator(page=seq + 1),
    )


def ndjson(request: httpx.Request) -> list[dict]:
    return [json.loads(line) for line in request.content.decode("utf-8").splitlines()]


# ---- mapping 文件 ----


@pytest.mark.parametrize("name", [DOC_META, CHUNKS])
def test_index_definition_is_strict_single_shard_and_uses_the_project_analyzer(name):
    definition = load_index_definition(name)

    assert definition["mappings"]["dynamic"] == "strict"
    assert definition["settings"]["index"]["number_of_shards"] == 1
    assert definition["settings"]["index"]["number_of_replicas"] == 0
    # BM25 参数显式写出：它们是实验参数
    assert definition["settings"]["index"]["similarity"]["default"] == {
        "type": "BM25",
        "k1": 1.2,
        "b": 0.75,
    }
    # 附录 A13：分词用 smartcn。字段只引用项目自己的名字 docmgr_text
    analyzer = definition["settings"]["analysis"]["analyzer"]["docmgr_text"]
    assert analyzer == {"type": "smartcn"}
    text_fields = [
        field for field in definition["mappings"]["properties"].values() if field["type"] == "text"
    ]
    assert text_fields and all(field["analyzer"] == "docmgr_text" for field in text_fields)


def test_chunks_fields_are_exactly_the_chunk_contract():
    properties = load_index_definition(CHUNKS)["mappings"]["properties"]

    # mapping 是 strict 的：字段与契约不一致，写入就会被拒绝
    assert set(properties) == set(Chunk.model_fields)
    assert properties["source_type"]["type"] == "keyword"
    assert properties["document_id"]["type"] == "keyword"
    # 来源定位只存储、不索引
    assert properties["locator"] == {"type": "object", "enabled": False}


def test_file_name_lives_only_in_doc_meta():
    # 附录 A8：文件名不冗余写进每个片段，否则同一文件的文件名得分会重复累加
    assert "filename" not in load_index_definition(CHUNKS)["mappings"]["properties"]
    assert set(load_index_definition(DOC_META)["mappings"]["properties"]) == {
        "document_id",
        "filename",
        "tags",
    }


@pytest.mark.parametrize("name", [DOC_META, CHUNKS])
def test_no_permission_fields_in_the_index(name):
    # 附录 A10：权限不写进索引
    properties = load_index_definition(name)["mappings"]["properties"]

    assert not {"owner_id", "shared_with", "deleted_at"} & set(properties)


def test_unknown_index_name_is_rejected(server):
    with pytest.raises(ValueError):
        load_index_definition("users")
    with pytest.raises(ValueError):
        server.client().index_name("users")


# ---- 创建索引 ----


def test_ensure_indices_creates_what_is_missing(server):
    server.reply("HEAD", "/doc_meta", 404)
    server.reply("HEAD", "/chunks", 404)

    created = ensure_indices(server.client())

    assert created == [DOC_META, CHUNKS]
    assert server.calls() == [
        ("HEAD", "/doc_meta"),
        ("PUT", "/doc_meta"),
        ("HEAD", "/chunks"),
        ("PUT", "/chunks"),
    ]
    assert json.loads(server.requests[1].content) == load_index_definition(DOC_META)
    assert json.loads(server.requests[3].content) == load_index_definition(CHUNKS)


def test_ensure_indices_leaves_existing_indices_alone(server):
    server.reply("HEAD", "/chunks", 404)

    created = ensure_indices(server.client())

    assert created == [CHUNKS]
    assert ("PUT", "/doc_meta") not in server.calls()


def test_ensure_indices_tolerates_losing_the_creation_race(server):
    server.reply("HEAD", "/doc_meta", 404)
    server.reply(
        "PUT",
        "/doc_meta",
        400,
        {"error": {"type": "resource_already_exists_exception", "reason": "already exists"}},
    )

    assert ensure_indices(server.client()) == []


def test_ensure_indices_reports_a_rejected_mapping(server):
    server.reply("HEAD", "/doc_meta", 404)
    server.reply(
        "PUT",
        "/doc_meta",
        400,
        {"error": {"type": "illegal_argument_exception", "reason": "Unknown tokenizer"}},
    )

    # 典型情况：没有安装 analysis-smartcn 插件
    with pytest.raises(TextIndexError, match="Unknown tokenizer") as excinfo:
        ensure_indices(server.client())
    assert excinfo.value.retryable is False


def test_index_prefix_is_applied_everywhere(server):
    client = server.client(prefix="test_ab12_")
    server.reply("HEAD", "/test_ab12_doc_meta", 404)
    server.reply("HEAD", "/test_ab12_chunks", 404)

    ensure_indices(client)
    index_document(client, document_id=DOCUMENT_ID, parse_version=VERSION, chunks=[make_chunk(0)])
    index_doc_meta(client, document_id=DOCUMENT_ID, filename="a.pdf", tags=[])
    delete_document(client, DOCUMENT_ID)

    paths = {path for _, path in server.calls()}
    assert all(path == "/_bulk" or path.startswith("/test_ab12_") for path in paths)
    bulk = next(r for r in server.requests if r.url.path == "/_bulk")
    assert ndjson(bulk)[0]["index"]["_index"] == "test_ab12_chunks"


@pytest.mark.parametrize("prefix", ["Upper", "_leading", "-leading", "has space", "中文"])
def test_invalid_index_prefix_is_rejected(prefix):
    with pytest.raises(ValueError):
        OpenSearchClient("http://localhost:9200", timeout_seconds=1.0, index_prefix=prefix)


# ---- 写入片段 ----


def test_index_document_deletes_other_versions_first_then_writes(server):
    chunks = [make_chunk(0), make_chunk(1)]

    index_document(server.client(), document_id=DOCUMENT_ID, parse_version=VERSION, chunks=chunks)

    assert server.calls() == [("POST", "/chunks/_delete_by_query"), ("POST", "/_bulk")]
    delete, bulk = server.requests
    # 只删这个文档、且只删别的版本
    assert json.loads(delete.content) == {
        "query": {
            "bool": {
                "filter": [{"term": {"document_id": str(DOCUMENT_ID)}}],
                "must_not": [{"term": {"parse_version": VERSION}}],
            }
        }
    }
    assert delete.url.params["refresh"] == "true"
    assert bulk.url.params["refresh"] == "true"


def test_bulk_body_uses_chunk_id_as_the_document_id(server):
    chunks = [make_chunk(0), make_chunk(1)]

    index_document(server.client(), document_id=DOCUMENT_ID, parse_version=VERSION, chunks=chunks)

    bulk = server.requests[-1]
    assert bulk.headers["content-type"] == "application/x-ndjson"
    assert bulk.content.endswith(b"\n")
    lines = ndjson(bulk)
    # 一个片段两行：动作行 + 数据行。_id 是 chunk_id，所以重复写入是覆盖
    assert [line["index"] for line in lines[0::2]] == [
        {"_index": "chunks", "_id": chunk.chunk_id} for chunk in chunks
    ]
    assert lines[1::2] == [chunk.model_dump(mode="json") for chunk in chunks]
    assert lines[1]["locator"] == {"type": "pdf_page", "page": 1}
    # 中文原样写出，不转成 \uXXXX
    assert "片段0".encode() in bulk.content


def test_indexing_the_same_chunks_twice_sends_identical_requests(server):
    chunks = [make_chunk(0), make_chunk(1)]
    client = server.client()

    index_document(client, document_id=DOCUMENT_ID, parse_version=VERSION, chunks=chunks)
    index_document(client, document_id=DOCUMENT_ID, parse_version=VERSION, chunks=chunks)

    first, second = server.requests[1], server.requests[3]
    assert first.content == second.content


def test_no_chunks_only_removes_other_versions(server):
    index_document(server.client(), document_id=DOCUMENT_ID, parse_version=VERSION, chunks=[])

    assert server.calls() == [("POST", "/chunks/_delete_by_query")]


def test_large_documents_are_written_in_batches(server, monkeypatch):
    monkeypatch.setattr(indexer_module, "BULK_BATCH_SIZE", 2)
    chunks = [make_chunk(seq) for seq in range(5)]

    index_document(server.client(), document_id=DOCUMENT_ID, parse_version=VERSION, chunks=chunks)

    bulks = [r for r in server.requests if r.url.path == "/_bulk"]
    assert [len(ndjson(r)) // 2 for r in bulks] == [2, 2, 1]
    written = [line["index"]["_id"] for r in bulks for line in ndjson(r)[0::2]]
    assert written == [chunk.chunk_id for chunk in chunks]


@pytest.mark.parametrize(
    "stranger",
    [
        make_chunk(1, document_id=OTHER_DOCUMENT_ID),
        make_chunk(1, version="c300o50-bbbbbbbbbbbb"),
    ],
)
def test_chunk_of_another_document_or_version_is_refused_before_anything_is_sent(server, stranger):
    with pytest.raises(ValueError):
        index_document(
            server.client(),
            document_id=DOCUMENT_ID,
            parse_version=VERSION,
            chunks=[make_chunk(0), stranger],
        )

    assert server.requests == []


def test_rejected_chunk_in_bulk_is_an_error_not_a_silent_loss(server):
    chunk = make_chunk(0)
    server.reply(
        "POST",
        "/_bulk",
        200,
        {
            "errors": True,
            "items": [
                {
                    "index": {
                        "_id": chunk.chunk_id,
                        "status": 400,
                        "error": {
                            "type": "strict_dynamic_mapping_exception",
                            "reason": "mapping set to strict",
                        },
                    }
                }
            ],
        },
    )

    # 批量接口整体返回 200，单个片段的失败藏在应答里
    with pytest.raises(TextIndexError, match="strict_dynamic_mapping_exception") as excinfo:
        index_document(
            server.client(), document_id=DOCUMENT_ID, parse_version=VERSION, chunks=[chunk]
        )
    assert chunk.chunk_id in excinfo.value.message
    assert excinfo.value.retryable is False


def test_refresh_can_be_turned_off_for_bulk_rebuilds(server):
    index_document(
        server.client(),
        document_id=DOCUMENT_ID,
        parse_version=VERSION,
        chunks=[make_chunk(0)],
        refresh=False,
    )

    assert [r.url.params["refresh"] for r in server.requests] == ["false", "false"]


def test_locator_of_any_type_is_written_as_is(server):
    chunk = Chunk.build(
        document_id=DOCUMENT_ID,
        parse_version=VERSION,
        seq=0,
        source_type="ocr",
        text="识别出的文字",
        locator=DocxParaLocator(para_index=7),
    )

    index_document(server.client(), document_id=DOCUMENT_ID, parse_version=VERSION, chunks=[chunk])

    data = ndjson(server.requests[-1])[1]
    assert data["source_type"] == "ocr"
    assert data["locator"] == {"type": "docx_para", "para_index": 7}


# ---- 删除时的部分失败 ----


@pytest.mark.parametrize(
    "result",
    [
        {"deleted": 1, "failures": [{"index": "chunks", "status": 500}]},
        {"deleted": 1, "version_conflicts": 2, "failures": []},
    ],
)
def test_partial_delete_is_a_retryable_error(server, result):
    server.reply("POST", "/chunks/_delete_by_query", 200, result)

    with pytest.raises(TextIndexUnavailable) as excinfo:
        delete_document(server.client(), DOCUMENT_ID)
    assert excinfo.value.retryable is True
    # 片段没删干净时不继续删 doc_meta：留着它，下次重试整个再来一遍
    assert ("DELETE", f"/doc_meta/_doc/{DOCUMENT_ID}") not in server.calls()


# ---- doc_meta ----


def test_index_doc_meta_overwrites_by_document_id(server):
    index_doc_meta(
        server.client(), document_id=DOCUMENT_ID, filename="年度报告.pdf", tags=["财务", "2026"]
    )

    (request,) = server.requests
    assert (request.method, request.url.path) == ("PUT", f"/doc_meta/_doc/{DOCUMENT_ID}")
    assert request.url.params["refresh"] == "true"
    assert json.loads(request.content) == {
        "document_id": str(DOCUMENT_ID),
        "filename": "年度报告.pdf",
        "tags": ["财务", "2026"],
    }


# ---- 删除文档 ----


def test_delete_document_removes_it_from_both_indices(server):
    delete_document(server.client(), DOCUMENT_ID)

    assert server.calls() == [
        ("POST", "/chunks/_delete_by_query"),
        ("DELETE", f"/doc_meta/_doc/{DOCUMENT_ID}"),
    ]
    # 这次不限版本：这个文档的片段全部删除
    assert json.loads(server.requests[0].content) == {
        "query": {"term": {"document_id": str(DOCUMENT_ID)}}
    }
    assert all(r.url.params["refresh"] == "true" for r in server.requests)


def test_deleting_a_document_that_was_never_indexed_is_not_an_error(server):
    server.reply("POST", "/chunks/_delete_by_query", 200, {"deleted": 0, "failures": []})
    server.reply("DELETE", f"/doc_meta/_doc/{DOCUMENT_ID}", 404, {"result": "not_found"})

    delete_document(server.client(), DOCUMENT_ID)


# ---- 故障：必须能和“没有数据”区分开 ----


def test_connection_failure_is_unavailable_and_retryable():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"connection refused to {HOST}:9200", request=request)

    client = OpenSearchClient(
        f"http://{HOST}:9200", timeout_seconds=1.0, transport=httpx.MockTransport(refuse)
    )

    with pytest.raises(TextIndexUnavailable) as excinfo:
        delete_document(client, DOCUMENT_ID)
    assert excinfo.value.retryable is True
    # 失败原因可能展示给用户：不带内部主机名和端口
    assert HOST not in excinfo.value.message
    assert "9200" not in excinfo.value.message


def test_timeout_is_unavailable():
    def too_slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = OpenSearchClient(
        f"http://{HOST}:9200", timeout_seconds=1.0, transport=httpx.MockTransport(too_slow)
    )

    with pytest.raises(TextIndexUnavailable):
        ensure_indices(client)


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_server_side_failure_is_unavailable_and_retryable(server, status):
    server.reply("POST", "/chunks/_delete_by_query", status, {"error": "busy"})

    with pytest.raises(TextIndexUnavailable) as excinfo:
        index_document(
            server.client(), document_id=DOCUMENT_ID, parse_version=VERSION, chunks=[make_chunk(0)]
        )
    assert excinfo.value.retryable is True
    # 删除旧版本失败时不继续写入
    assert ("POST", "/_bulk") not in server.calls()


def test_missing_index_is_an_error_not_an_empty_result(server):
    server.reply(
        "POST",
        "/chunks/_delete_by_query",
        404,
        {"error": {"type": "index_not_found_exception", "reason": "no such index [chunks]"}},
    )

    with pytest.raises(TextIndexError, match="index_not_found_exception") as excinfo:
        delete_document(server.client(), DOCUMENT_ID)
    assert excinfo.value.retryable is False


def test_non_json_error_body_is_handled(server):
    server.responses[("PUT", f"/doc_meta/_doc/{DOCUMENT_ID}")] = httpx.Response(
        400, text="<html>bad request</html>"
    )

    with pytest.raises(TextIndexError, match="HTTP 400"):
        index_doc_meta(server.client(), document_id=DOCUMENT_ID, filename="a.pdf", tags=[])


def test_unavailable_is_a_kind_of_text_index_error():
    # 调用方只想知道“索引操作失败了”时，接住 TextIndexError 一种就够
    assert issubclass(TextIndexUnavailable, TextIndexError)
