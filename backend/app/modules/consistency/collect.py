"""M13：收集三方的现状。只读，不修改任何东西。"""

import time
import uuid
from pathlib import Path
from typing import Any

from shared.storage_keys import KEY_RE
from shared.tasks import (
    STATUS_PENDING,
    STATUS_PROCESSING,
    TASK_CLEANUP,
    TASK_OCR,
    TASK_PARSE,
)
from shared.text_index import (
    CHUNKS,
    DOC_META,
    INDEX_NAMES,
    OpenSearchClient,
    TextIndexError,
    TextIndexUnavailable,
    load_index_definition,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentChunk, ImageAsset, OCRResult, ProcessingTask
from app.modules.consistency.model import (
    DbChunk,
    DbDocument,
    DbOcrResult,
    DbState,
    DiskFile,
    DiskState,
    IndexChunk,
    IndexState,
    locator_key,
)
from app.modules.documents.tags import tags_by_document

# 与 app/modules/storage/local.py 一致：上传临时文件放在这里，名字是 32 位十六进制 + .part
TMP_DIR_NAME = ".tmp"
_SCAN_PAGE_SIZE = 1000
_INDEX_NOT_FOUND = "index_not_found_exception"


# ---- 数据库 ----


def collect_db(session: Session) -> DbState:
    state = DbState()
    documents = list(session.scalars(select(Document)))
    tags = tags_by_document(session, [d.id for d in documents])
    cleanup_pending = set(
        session.scalars(
            select(ProcessingTask.document_id).where(
                ProcessingTask.task_type == TASK_CLEANUP,
                ProcessingTask.status.in_((STATUS_PENDING, STATUS_PROCESSING)),
            )
        )
    )
    busy = set(
        session.scalars(
            select(ProcessingTask.document_id).where(
                ProcessingTask.task_type.in_((TASK_PARSE, TASK_OCR)),
                ProcessingTask.status.in_((STATUS_PENDING, STATUS_PROCESSING)),
            )
        )
    )
    for document in documents:
        state.documents[str(document.id)] = DbDocument(
            id=str(document.id),
            deleted=document.deleted_at is not None,
            storage_key=document.storage_key,
            parse_version=document.parse_version,
            filename=document.filename,
            tags=tuple(sorted(tags.get(document.id, []))),
            cleanup_pending=document.id in cleanup_pending,
            busy=document.id in busy,
            status=document.status,
            mime_type=document.mime_type,
        )

    for row in session.execute(
        select(
            DocumentChunk.chunk_id,
            DocumentChunk.document_id,
            DocumentChunk.parse_version,
            DocumentChunk.source_type,
            DocumentChunk.locator,
        )
    ):
        state.chunks.append(
            DbChunk(
                chunk_id=row.chunk_id,
                document_id=str(row.document_id),
                parse_version=row.parse_version,
                source_type=row.source_type,
                locator=row.locator,
            )
        )

    for row in session.execute(select(OCRResult.id, OCRResult.document_id, OCRResult.locator)):
        state.ocr_results.append(
            DbOcrResult(id=str(row.id), document_id=str(row.document_id), locator=row.locator)
        )

    for row in session.execute(select(ImageAsset.document_id, ImageAsset.sha256)):
        state.image_assets[str(row.document_id)] = row.sha256

    versions = {d.id: d.parse_version for d in state.documents.values()}
    for row in session.execute(
        select(ProcessingTask.document_id, ProcessingTask.payload).where(
            ProcessingTask.task_type == TASK_OCR
        )
    ):
        document_id = str(row.document_id)
        payload: dict[str, Any] = row.payload or {}
        if payload.get("parse_version") == versions.get(document_id) and "locator" in payload:
            state.ocr_targets.setdefault(document_id, set()).add(locator_key(payload["locator"]))
    return state


# ---- 磁盘 ----


def collect_disk(root: Path, *, now: float | None = None) -> DiskState:
    """遍历存储根目录。不跟随符号链接；目录本身不算文件。"""
    state = DiskState()
    root = root.resolve()
    if not root.is_dir():
        return state
    now = time.time() if now is None else now
    for path in sorted(root.rglob("*")):
        if path.is_dir() and not path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        try:
            age = now - path.lstat().st_mtime
        except FileNotFoundError:  # 遍历期间被删掉
            continue
        file = DiskFile(path=path, relative=relative, age_seconds=age)
        if path.is_symlink():
            state.unknown.append(file)
        elif KEY_RE.fullmatch(relative):
            state.stored[relative] = file
        elif path.parent == root / TMP_DIR_NAME and path.suffix == ".part":
            state.temp_files.append(file)
        else:
            state.unknown.append(file)
    return state


# ---- 索引 ----


def _scan(client: OpenSearchClient, logical_name: str, fields: list[str], sort_field: str):
    """按 sort_field 分页取出整个索引（search_after），逐条产出 hit。"""
    path = f"/{client.index_name(logical_name)}/_search"
    after: list[Any] | None = None
    while True:
        body: dict[str, Any] = {
            "size": _SCAN_PAGE_SIZE,
            "track_total_hits": False,
            "_source": fields,
            "sort": [{sort_field: "asc"}],
            "query": {"match_all": {}},
        }
        if after is not None:
            body["search_after"] = after
        hits = client.request("POST", path, json=body).json()["hits"]["hits"]
        yield from hits
        if len(hits) < _SCAN_PAGE_SIZE:
            return
        after = hits[-1]["sort"]


def _comparable(field: dict[str, Any]) -> dict[str, Any]:
    """mapping 里一个字段的可比较部分。OpenSearch 返回的 mapping 与提交的写法基本一致。"""
    keys = ("type", "analyzer", "enabled")
    result = {k: field.get(k) for k in keys if k in field}
    if "fields" in field:
        result["fields"] = {name: _comparable(sub) for name, sub in field["fields"].items()}
    return result


def check_structure(client: OpenSearchClient, logical_name: str) -> list[str]:
    """与版本库里的 mapping 文件比较，返回不一致的地方（空列表表示一致）。"""
    expected = load_index_definition(logical_name)
    index = client.index_name(logical_name)
    problems: list[str] = []

    mapping = client.request("GET", f"/{index}/_mapping").json()
    actual = next(iter(mapping.values()))["mappings"]
    if str(actual.get("dynamic")) != str(expected["mappings"]["dynamic"]):
        problems.append(f"dynamic 为 {actual.get('dynamic')}，应为 strict")
    expected_props = expected["mappings"]["properties"]
    actual_props = actual.get("properties", {})
    for name in sorted(set(expected_props) | set(actual_props)):
        if name not in actual_props:
            problems.append(f"缺少字段 {name}")
        elif name not in expected_props:
            problems.append(f"多出字段 {name}")
        elif _comparable(actual_props[name]) != _comparable(expected_props[name]):
            problems.append(f"字段 {name} 的定义不同")

    settings = next(iter(client.request("GET", f"/{index}/_settings").json().values()))
    actual_index = settings["settings"]["index"]
    expected_index = expected["settings"]["index"]
    analyzer = actual_index.get("analysis", {}).get("analyzer", {}).get("docmgr_text", {})
    expected_analyzer = expected["settings"]["analysis"]["analyzer"]["docmgr_text"]
    if analyzer.get("type") != expected_analyzer["type"]:
        problems.append(
            f"分词器 docmgr_text 为 {analyzer.get('type')}，应为 {expected_analyzer['type']}"
        )
    similarity = actual_index.get("similarity", {}).get("default", {})
    for key, value in expected_index["similarity"]["default"].items():
        if str(similarity.get(key)) != str(value):
            problems.append(f"BM25 参数 {key} 为 {similarity.get(key)}，应为 {value}")
    return problems


def collect_index(client: OpenSearchClient) -> IndexState:
    state = IndexState()
    try:
        for logical_name in INDEX_NAMES:
            index = client.index_name(logical_name)
            if client.request("HEAD", f"/{index}", also_accept={404}).status_code == 404:
                state.missing_indices.append(logical_name)
                continue
            problems = check_structure(client, logical_name)
            if problems:
                state.structure_mismatch[logical_name] = problems

        if DOC_META not in state.missing_indices:
            for hit in _scan(client, DOC_META, ["document_id", "filename", "tags"], "document_id"):
                source = hit["_source"]
                state.meta[str(source.get("document_id", hit["_id"]))] = (
                    source.get("filename", ""),
                    tuple(sorted(source.get("tags", []))),
                )
        if CHUNKS not in state.missing_indices:
            for hit in _scan(
                client, CHUNKS, ["chunk_id", "document_id", "parse_version"], "chunk_id"
            ):
                source = hit["_source"]
                chunk_id = str(source.get("chunk_id", hit["_id"]))
                state.chunks[chunk_id] = IndexChunk(
                    chunk_id=chunk_id,
                    document_id=str(source.get("document_id", "")),
                    parse_version=str(source.get("parse_version", "")),
                )
    except (TextIndexUnavailable, TextIndexError) as exc:
        if isinstance(exc, TextIndexError) and _INDEX_NOT_FOUND in exc.message:
            # 检查过程中索引被删掉了：如实记为缺失，而不是当成服务故障
            state.missing_indices = sorted(set(state.missing_indices) | set(INDEX_NAMES))
            return state
        return IndexState(available=False, error=exc.message)
    return state


def parse_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None
