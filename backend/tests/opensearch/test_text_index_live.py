"""T13 🧪：对着真实的 OpenSearch 验证文本索引。

需要一个装了 analysis-smartcn 插件的 OpenSearch，并设置环境变量 TEST_OPENSEARCH_URL
（例如 http://localhost:9200）。不设置时本文件的测试全部跳过，算“未运行”。

每次运行使用独立的索引名前缀，结束时只删除自己建的索引，不碰其他数据。

DEVPLAN 要求的两项：重复索引不产生重复数据；删除后查不到。
"""

import os
import uuid

import pytest
from shared.contracts import Chunk, PdfPageLocator

from app.modules.text_index import (
    CHUNKS,
    DOC_META,
    INDEX_NAMES,
    OpenSearchClient,
    TextIndexError,
    delete_document,
    ensure_indices,
    index_doc_meta,
    index_document,
)

OPENSEARCH_URL = os.environ.get("TEST_OPENSEARCH_URL")

pytestmark = pytest.mark.skipif(
    not OPENSEARCH_URL, reason="未设置 TEST_OPENSEARCH_URL，需要真实 OpenSearch 的测试未运行"
)

V1 = "c500o50-aaaaaaaaaaaa"
V2 = "c300o50-bbbbbbbbbbbb"


@pytest.fixture
def client():
    prefix = f"test_{uuid.uuid4().hex[:10]}_"
    with OpenSearchClient(OPENSEARCH_URL, timeout_seconds=30.0, index_prefix=prefix) as c:
        ensure_indices(c)
        try:
            yield c
        finally:
            for name in INDEX_NAMES:
                c.request("DELETE", f"/{c.index_name(name)}", also_accept={404})


def make_chunks(document_id: uuid.UUID, version: str, texts: list[str]) -> list[Chunk]:
    return [
        Chunk.build(
            document_id=document_id,
            parse_version=version,
            seq=seq,
            source_type="body",
            text=text,
            locator=PdfPageLocator(page=seq + 1),
        )
        for seq, text in enumerate(texts)
    ]


def count(client: OpenSearchClient, name: str, query: dict | None = None) -> int:
    body = {"query": query or {"match_all": {}}}
    return client.request("POST", f"/{client.index_name(name)}/_count", json=body).json()["count"]


def search_ids(client: OpenSearchClient, name: str, query: dict) -> list[str]:
    response = client.request(
        "POST", f"/{client.index_name(name)}/_search", json={"query": query, "size": 100}
    )
    return [hit["_id"] for hit in response.json()["hits"]["hits"]]


def of_document(document_id: uuid.UUID) -> dict:
    return {"term": {"document_id": str(document_id)}}


# ---- 创建索引 ----


def test_ensure_indices_is_idempotent(client):
    # fixture 里已经建过一次
    assert ensure_indices(client) == []
    assert count(client, CHUNKS) == 0
    assert count(client, DOC_META) == 0


# ---- 🧪 重复索引不产生重复数据 ----


def test_indexing_the_same_document_twice_does_not_duplicate(client):
    document_id = uuid.uuid4()
    chunks = make_chunks(document_id, V1, ["第一页的内容", "第二页的内容", "第三页的内容"])

    index_document(client, document_id=document_id, parse_version=V1, chunks=chunks)
    index_document(client, document_id=document_id, parse_version=V1, chunks=chunks)

    assert count(client, CHUNKS, of_document(document_id)) == 3
    assert sorted(search_ids(client, CHUNKS, of_document(document_id))) == sorted(
        c.chunk_id for c in chunks
    )


def test_reindexing_with_a_new_parse_version_replaces_the_old_chunks(client):
    document_id = uuid.uuid4()
    old = make_chunks(document_id, V1, ["旧片段一", "旧片段二", "旧片段三"])
    new = make_chunks(document_id, V2, ["新片段一", "新片段二"])

    index_document(client, document_id=document_id, parse_version=V1, chunks=old)
    index_document(client, document_id=document_id, parse_version=V2, chunks=new)

    assert sorted(search_ids(client, CHUNKS, of_document(document_id))) == sorted(
        c.chunk_id for c in new
    )


def test_reindexing_one_document_leaves_other_documents_alone(client):
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    index_document(
        client, document_id=theirs, parse_version=V1, chunks=make_chunks(theirs, V1, ["别人的"])
    )
    index_document(
        client, document_id=mine, parse_version=V1, chunks=make_chunks(mine, V1, ["我的旧版"])
    )

    index_document(
        client, document_id=mine, parse_version=V2, chunks=make_chunks(mine, V2, ["我的新版"])
    )

    assert count(client, CHUNKS, of_document(theirs)) == 1
    assert count(client, CHUNKS, of_document(mine)) == 1


def test_doc_meta_written_twice_is_one_record_with_the_latest_values(client):
    document_id = uuid.uuid4()

    index_doc_meta(client, document_id=document_id, filename="草稿.docx", tags=["草稿"])
    index_doc_meta(client, document_id=document_id, filename="草稿.docx", tags=["定稿", "财务"])

    assert count(client, DOC_META, of_document(document_id)) == 1
    assert search_ids(client, DOC_META, {"term": {"tags.raw": "定稿"}}) == [str(document_id)]
    assert search_ids(client, DOC_META, {"term": {"tags.raw": "草稿"}}) == []


# ---- 🧪 删除后查不到 ----


def test_deleted_document_cannot_be_found_in_either_index(client):
    document_id, other = uuid.uuid4(), uuid.uuid4()
    index_document(
        client,
        document_id=document_id,
        parse_version=V1,
        chunks=make_chunks(document_id, V1, ["智能文档管理系统的设计", "检索结果融合"]),
    )
    index_doc_meta(client, document_id=document_id, filename="设计说明.pdf", tags=["设计"])
    index_document(
        client, document_id=other, parse_version=V1, chunks=make_chunks(other, V1, ["文档管理"])
    )
    index_doc_meta(client, document_id=other, filename="其他文档.pdf", tags=[])
    assert count(client, CHUNKS, of_document(document_id)) == 2

    delete_document(client, document_id)

    # 不等待、不重试：删除返回后立刻查
    assert count(client, CHUNKS, of_document(document_id)) == 0
    assert count(client, DOC_META, of_document(document_id)) == 0
    hits = search_ids(client, CHUNKS, {"match": {"text": "文档管理"}})
    assert hits and all(hit.startswith(str(other)) for hit in hits)
    # 别的文档不受影响
    assert count(client, DOC_META, of_document(other)) == 1


def test_deleting_twice_or_deleting_an_unknown_document_is_fine(client):
    document_id = uuid.uuid4()
    index_doc_meta(client, document_id=document_id, filename="a.pdf", tags=[])

    delete_document(client, document_id)
    delete_document(client, document_id)
    delete_document(client, uuid.uuid4())

    assert count(client, DOC_META) == 0


# ---- 分词与字段 ----


def test_chinese_text_is_searchable_by_word(client):
    document_id = uuid.uuid4()
    chunks = make_chunks(
        document_id, V1, ["本系统支持扫描件的文字识别与全文检索。", "BM25 is the baseline."]
    )
    index_document(client, document_id=document_id, parse_version=V1, chunks=chunks)

    assert search_ids(client, CHUNKS, {"match": {"text": "全文检索"}}) == [chunks[0].chunk_id]
    assert search_ids(client, CHUNKS, {"match": {"text": "baseline"}}) == [chunks[1].chunk_id]
    assert search_ids(client, CHUNKS, {"match": {"text": "量子计算"}}) == []


def test_analyzer_is_smartcn_and_splits_chinese_into_words(client):
    response = client.request(
        "POST",
        f"/{client.index_name(CHUNKS)}/_analyze",
        json={"analyzer": "docmgr_text", "text": "智能文档管理系统"},
    )
    tokens = [token["token"] for token in response.json()["tokens"]]

    # 默认分词器会把中文切成一个个单字；smartcn 应当切出多字的词
    assert any(len(token) > 1 for token in tokens)
    assert "".join(tokens) == "智能文档管理系统"


def test_file_name_and_tags_are_searchable(client):
    document_id = uuid.uuid4()
    index_doc_meta(client, document_id=document_id, filename="2026年度财务报告.pdf", tags=["审计"])

    assert search_ids(client, DOC_META, {"match": {"filename": "财务报告"}}) == [str(document_id)]
    assert search_ids(client, DOC_META, {"match": {"tags": "审计"}}) == [str(document_id)]


def test_source_type_filter_separates_body_from_ocr(client):
    # B1 / B2 两组实验只差这一个过滤条件（附录 A8）
    document_id = uuid.uuid4()
    body = make_chunks(document_id, V1, ["正文里的检索"])
    ocr = Chunk.build(
        document_id=document_id,
        parse_version=V1,
        seq=1,
        source_type="ocr",
        text="图片里的检索",
        locator=PdfPageLocator(page=2),
    )
    index_document(client, document_id=document_id, parse_version=V1, chunks=[*body, ocr])

    def matching(source_types: list[str]) -> list[str]:
        return sorted(
            search_ids(
                client,
                CHUNKS,
                {
                    "bool": {
                        "must": [{"match": {"text": "检索"}}],
                        "filter": [{"terms": {"source_type": source_types}}],
                    }
                },
            )
        )

    assert matching(["body"]) == [body[0].chunk_id]
    assert matching(["body", "ocr"]) == sorted([body[0].chunk_id, ocr.chunk_id])


def test_body_chunks_survive_a_later_write_of_ocr_chunks_in_the_same_version(client):
    # 正文片段和 OCR 片段分两次写入，后一次不能把前一次的删掉
    document_id = uuid.uuid4()
    body = make_chunks(document_id, V1, ["正文片段"])
    ocr = Chunk.build(
        document_id=document_id,
        parse_version=V1,
        seq=1,
        source_type="ocr",
        text="OCR 片段",
        locator=PdfPageLocator(page=2),
    )

    index_document(client, document_id=document_id, parse_version=V1, chunks=body)
    index_document(client, document_id=document_id, parse_version=V1, chunks=[ocr])

    assert count(client, CHUNKS, of_document(document_id)) == 2


def test_strict_mapping_rejects_unknown_fields(client):
    with pytest.raises(TextIndexError, match="strict_dynamic_mapping_exception"):
        client.request(
            "PUT",
            f"/{client.index_name(DOC_META)}/_doc/x",
            json={"document_id": "x", "filename": "a.pdf", "tags": [], "owner_id": "someone"},
        )
