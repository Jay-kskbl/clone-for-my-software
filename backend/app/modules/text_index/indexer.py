"""M8：往两个索引里写入和删除。

幂等靠确定性 ID（附录 A7）：
- chunks 索引里每条数据的 _id 就是 chunk_id，同一个片段写两次是覆盖，不是追加；
- doc_meta 索引里每条数据的 _id 就是 document_id。

所有写入默认立即刷新（refresh）：写完马上能搜到、删完马上搜不到。
代价是写入变慢，毕设的数据规模下可以接受；批量重建索引时可以传 refresh=False。

权限信息不进索引（附录 A10）：谁能看到哪个文档由数据库决定，检索时用
“可访问的 document_id 集合”过滤，返回前再用数据库校验一次。
"""

import json
from collections.abc import Iterator, Sequence
from typing import Any
from uuid import UUID

import httpx
from shared.contracts import Chunk

from app.modules.text_index.client import CHUNKS, DOC_META, OpenSearchClient
from app.modules.text_index.errors import TextIndexError, TextIndexUnavailable

# 一次批量请求最多带多少个片段。片段上限 500 字左右，500 个大约 1 MB
BULK_BATCH_SIZE = 500

_NDJSON = {"Content-Type": "application/x-ndjson"}


def _refresh(refresh: bool) -> dict[str, str]:
    return {"refresh": "true" if refresh else "false"}


def _delete_by_query(
    client: OpenSearchClient, index: str, query: dict[str, Any], *, refresh: bool
) -> int:
    """删除 index 里满足 query 的全部数据，返回删掉的条数。"""
    response = client.request(
        "POST",
        f"/{index}/_delete_by_query",
        # conflicts=proceed：遇到正在被别的请求修改的数据时不中途放弃，删完其余的再报告
        params={**_refresh(refresh), "conflicts": "proceed"},
        json={"query": query},
    )
    result = response.json()
    if result.get("failures"):
        raise TextIndexUnavailable("检索服务删除数据时部分失败")
    if result.get("version_conflicts"):
        # 有数据在删除的同时被改动，没删掉。重试一次即可
        raise TextIndexUnavailable("检索服务删除数据时遇到并发修改，有数据未删除")
    return int(result.get("deleted", 0))


def _batches(chunks: Sequence[Chunk]) -> Iterator[Sequence[Chunk]]:
    for start in range(0, len(chunks), BULK_BATCH_SIZE):
        yield chunks[start : start + BULK_BATCH_SIZE]


def _bulk_body(index: str, chunks: Sequence[Chunk]) -> bytes:
    lines: list[str] = []
    for chunk in chunks:
        lines.append(json.dumps({"index": {"_index": index, "_id": chunk.chunk_id}}))
        # 写进索引的就是 Chunk 契约的全部字段，一个不多、一个不少（mapping 是 strict 的）
        lines.append(json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False))
    # 批量接口要求每一行（包括最后一行）都以换行结尾
    return ("\n".join(lines) + "\n").encode("utf-8")


def _check_bulk_result(response: httpx.Response) -> None:
    result = response.json()
    if not result.get("errors"):
        return
    for item in result.get("items", []):
        error = item.get("index", {}).get("error")
        if error:
            raise TextIndexError(
                f"检索服务拒绝了片段 {item['index'].get('_id')}"
                f"（{error.get('type')}：{error.get('reason')}）"
            )
    raise TextIndexError("检索服务报告批量写入有错误，但没有给出原因")


def index_document(
    client: OpenSearchClient,
    *,
    document_id: UUID,
    parse_version: str,
    chunks: Sequence[Chunk],
    refresh: bool = True,
) -> None:
    """把一个文档当前版本的片段写入 chunks 索引。

    先删除这个文档其他 parse_version 的片段，再写入这一批。
    同一批片段重复写入，结果与写一次相同。chunks 为空时只做删除。

    同一 parse_version 下已有的片段不会被删：正文片段和之后 OCR 产生的片段
    共用一个 parse_version，分两次写入，后一次不能把前一次的删掉。
    """
    for chunk in chunks:
        if chunk.document_id != document_id or chunk.parse_version != parse_version:
            raise ValueError(
                f"片段 {chunk.chunk_id} 不属于文档 {document_id} 的版本 {parse_version}"
            )

    index = client.index_name(CHUNKS)
    _delete_by_query(
        client,
        index,
        {
            "bool": {
                "filter": [{"term": {"document_id": str(document_id)}}],
                "must_not": [{"term": {"parse_version": parse_version}}],
            }
        },
        refresh=refresh,
    )
    for batch in _batches(chunks):
        response = client.request(
            "POST",
            "/_bulk",
            params=_refresh(refresh),
            content=_bulk_body(index, batch),
            headers=_NDJSON,
        )
        _check_bulk_result(response)


def index_doc_meta(
    client: OpenSearchClient,
    *,
    document_id: UUID,
    filename: str,
    tags: Sequence[str],
    refresh: bool = True,
) -> None:
    """写入（或整体覆盖）一个文档在 doc_meta 索引里的数据：文件名和标签。

    标签改动后要再调用一次，传入改动后的完整标签列表。
    """
    client.request(
        "PUT",
        f"/{client.index_name(DOC_META)}/_doc/{document_id}",
        params=_refresh(refresh),
        json={"document_id": str(document_id), "filename": filename, "tags": list(tags)},
    )


def delete_document(client: OpenSearchClient, document_id: UUID, *, refresh: bool = True) -> None:
    """删除一个文档在两个索引里的全部数据。文档本来就不在索引里时什么也不做。"""
    _delete_by_query(
        client,
        client.index_name(CHUNKS),
        {"term": {"document_id": str(document_id)}},
        refresh=refresh,
    )
    client.request(
        "DELETE",
        f"/{client.index_name(DOC_META)}/_doc/{document_id}",
        params=_refresh(refresh),
        also_accept={404},
    )
