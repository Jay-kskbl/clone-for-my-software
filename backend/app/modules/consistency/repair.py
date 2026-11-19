"""M13：按检查结果修复。只修调用方显式列出的类别。

以数据库为准（D9）：索引和磁盘向数据库看齐，不反过来改数据库里的文档记录。
每个修复动作执行前都再查一次数据库，确认情况没有在检查之后发生变化
（例如“没有记录的文件”在检查之后被一个正在完成的上传认领了）。

写索引一律立即刷新（refresh=true）：先删后写时，未刷新的数据删不掉（D26）。
"""

import logging
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

from pydantic import TypeAdapter
from shared.contracts import Chunk, SourceLocator
from shared.tasks import STATUS_PENDING, STATUS_PROCESSING, TASK_CLEANUP, TASK_OCR, TASK_PARSE
from shared.text_index import (
    CHUNKS,
    DOC_META,
    IMAGE_VECTORS,
    INDEX_NAMES,
    OpenSearchClient,
    delete_document,
    ensure_indices,
    index_doc_meta,
    write_chunks,
)
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    DocumentChunk,
    ImageAsset,
    ImageEmbedding,
    OCRResult,
    ProcessingTask,
)
from app.modules.consistency.collect import TMP_DIR_NAME, parse_uuid
from app.modules.consistency.model import (
    REPAIR_CLEANUP_TASKS,
    REPAIR_DB_CHUNKS,
    REPAIR_EMBEDDINGS,
    REPAIR_INDEX,
    REPAIR_KINDS,
    REPAIR_OCR_RESULTS,
    REPAIR_ORPHAN_FILES,
    REPAIR_REBUILD_INDICES,
    REPAIR_TEMP_FILES,
    Issue,
)
from app.modules.documents.tags import tags_by_document
from app.modules.storage import LocalStorage
from app.modules.vector_index import (
    VECTOR_DIM,
    delete_document_vectors,
    ensure_vector_index,
    index_image_vector,
)
from app.worker.handlers.embed import lock_content

logger = logging.getLogger(__name__)
_LOCATOR = TypeAdapter(SourceLocator)

# 执行顺序：先改数据库，再按数据库重建索引；重建全部索引时不必再逐个修
_ORDER = (
    REPAIR_DB_CHUNKS,
    REPAIR_OCR_RESULTS,
    REPAIR_CLEANUP_TASKS,
    REPAIR_REBUILD_INDICES,
    REPAIR_INDEX,
    # 在索引修复之后：重建向量索引时还要用到这些向量记录（被引用的不会被删，这里只是更稳妥）
    REPAIR_EMBEDDINGS,
    REPAIR_TEMP_FILES,
    REPAIR_ORPHAN_FILES,
)


def _busy(session: Session, document_id: uuid.UUID) -> bool:
    """文档有尚未完成的 parse 或 ocr 任务：片段和索引正在变化，此时不能动它。"""
    return bool(
        session.scalar(
            select(func.count())
            .select_from(ProcessingTask)
            .where(
                ProcessingTask.document_id == document_id,
                ProcessingTask.task_type.in_((TASK_PARSE, TASK_OCR)),
                ProcessingTask.status.in_((STATUS_PENDING, STATUS_PROCESSING)),
            )
        )
    )


@dataclass
class RepairReport:
    done: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


# T24d（D43）：--force 无条件重建时补进计划的那一项
FORCED_REBUILD_KIND = "forced_rebuild"


def plan(
    issues: Sequence[Issue], kinds: Iterable[str], *, force_rebuild: bool = False
) -> list[Issue]:
    """从检查结果里挑出要修的那些，按执行顺序排好。

    force_rebuild：检查没有发现索引缺失或结构不一致时也重建三个索引（T24d）。
    结构检查只比较字段类型、分词器类型和 BM25 参数，改了别的设置（例如 search_analyzer）
    发现不了，这时用它。只能和 rebuild-indices 一起用。
    """
    wanted = set(kinds)
    unknown = wanted - set(REPAIR_KINDS)
    if unknown:
        raise ValueError(f"未知的修复类别：{'、'.join(sorted(unknown))}")
    if force_rebuild and REPAIR_REBUILD_INDICES not in wanted:
        raise ValueError(f"强制重建只能和 {REPAIR_REBUILD_INDICES} 一起使用")
    selected = [i for i in issues if i.repair in wanted]
    if force_rebuild and not any(i.repair == REPAIR_REBUILD_INDICES for i in selected):
        selected.append(
            Issue(
                kind=FORCED_REBUILD_KIND,
                detail="按 --force 无条件重建三个索引（检查没有发现索引缺失或结构不一致）",
                repair=REPAIR_REBUILD_INDICES,
            )
        )
    return sorted(selected, key=lambda i: _ORDER.index(i.repair))  # type: ignore[arg-type]


# ---- 单个文档的索引 ----


def _current_chunks(session: Session, document: Document) -> list[Chunk]:
    if document.parse_version is None:
        return []
    rows = session.scalars(
        select(DocumentChunk)
        .where(
            DocumentChunk.document_id == document.id,
            DocumentChunk.parse_version == document.parse_version,
        )
        .order_by(DocumentChunk.seq)
    )
    return [
        Chunk(
            chunk_id=row.chunk_id,
            document_id=row.document_id,
            parse_version=row.parse_version,
            seq=row.seq,
            source_type=row.source_type,
            text=row.text,
            locator=_LOCATOR.validate_python(row.locator),
        )
        for row in rows
    ]


def reindex_document(session: Session, client: OpenSearchClient, document: Document) -> int:
    """按数据库重建一个文档在两个索引里的数据：先整体删掉，再写当前版本的片段和 doc_meta。

    返回写入的片段数。还没有解析版本的文档（等待解析，或解析失败）没有片段可写，但 doc_meta
    照样写：parse 任务在解析之前就写了 doc_meta，为的是正文解析失败的文件仍能按文件名搜到
    （handlers/parse.py 第 3 步）。重建不能把这一点丢掉——否则全量重建之后，解析失败的文件
    就从文件名检索里消失了，而检查又不会报告它。
    """
    delete_document(client, document.id)
    chunks = _current_chunks(session, document)
    write_chunks(client, chunks)
    tags = tags_by_document(session, [document.id]).get(document.id, [])
    index_doc_meta(client, document_id=document.id, filename=document.filename, tags=tags)
    return len(chunks)


def reindex_document_vectors(session: Session, client: OpenSearchClient, document: Document) -> int:
    """按数据库重建一个文档在图片向量索引里的数据（T21），返回写入的向量数。

    向量直接取自 image_embeddings，不重新调用 CLIP（D10）。同一内容有多个模型的向量时，
    用最近生成的那条（一致性检查不知道 CLIP 服务当前加载的是哪个模型）；
    还没有向量的图片跳过，由 embed 任务负责。
    """
    delete_document_vectors(client, document.id)
    written = 0
    for image in session.scalars(select(ImageAsset).where(ImageAsset.document_id == document.id)):
        embedding = session.scalars(
            select(ImageEmbedding)
            .where(ImageEmbedding.sha256 == image.sha256, ImageEmbedding.dim == VECTOR_DIM)
            .order_by(ImageEmbedding.created_at.desc(), ImageEmbedding.id)
            .limit(1)
        ).first()
        if embedding is None:
            continue
        index_image_vector(
            client,
            image_id=image.image_id,
            document_id=document.id,
            sha256=image.sha256,
            model_name=embedding.model_name,
            model_version=embedding.model_version,
            vector=list(embedding.vector),
        )
        written += 1
    return written


def _repair_index(
    session: Session, client: OpenSearchClient, document_ids: Iterable[str], report: RepairReport
) -> None:
    ensure_indices(client)
    ensure_vector_index(client)
    for raw_id in sorted(set(document_ids)):
        document_id = parse_uuid(raw_id)
        if document_id is None:
            # 索引里的 document_id 不是合法 UUID：只能按原样删掉
            client.request(
                "POST",
                f"/{client.index_name(CHUNKS)}/_delete_by_query",
                params={"refresh": "true", "conflicts": "proceed"},
                json={"query": {"term": {"document_id": raw_id}}},
            )
            client.request(
                "DELETE",
                f"/{client.index_name(DOC_META)}/_doc/{quote(raw_id, safe='')}",
                params={"refresh": "true"},
                also_accept={404},
            )
            client.request(
                "POST",
                f"/{client.index_name(IMAGE_VECTORS)}/_delete_by_query",
                params={"refresh": "true", "conflicts": "proceed"},
                json={"query": {"term": {"document_id": raw_id}}},
            )
            report.done.append(f"索引：删除了 document_id 为 {raw_id!r} 的残留")
            continue
        document = session.get(Document, document_id, populate_existing=True)
        if document is None or document.deleted_at is not None:
            delete_document(client, document_id)
            delete_document_vectors(client, document_id)
            report.done.append(f"索引：撤掉了文档 {document_id} 的残留数据")
        elif _busy(session, document.id):
            report.skipped.append(f"文档 {document_id} 正在解析或识别，没有重建它的索引")
        else:
            count = reindex_document(session, client, document)
            vectors = reindex_document_vectors(session, client, document)
            report.done.append(
                f"索引：按数据库重建了文档 {document_id}（{count} 个片段，{vectors} 个图片向量）"
            )


def rebuild_indices(session: Session, client: OpenSearchClient, report: RepairReport) -> None:
    """删掉三个索引（两个文本索引和图片向量索引），按版本库里的 mapping 重新创建，
    再把全部未删除的文档重新索引。

    mapping 或分词器改动后的重建入口（D26）。数据全部来自数据库，不重新解析、不重新 OCR（D9）。
    重建期间检索结果不完整。必须先停掉通用 Worker 和 OCR Worker：重建时索引会被删掉一会儿，
    而 OpenSearch 关闭了自动建索引（deploy/docker-compose.yml），这时 Worker 写索引会失败。
    """
    for name in (*INDEX_NAMES, IMAGE_VECTORS):
        client.request("DELETE", f"/{client.index_name(name)}", also_accept={404})
    ensure_indices(client)
    ensure_vector_index(client)
    documents = session.scalars(
        select(Document).where(Document.deleted_at.is_(None)).order_by(Document.created_at)
    )
    total_documents = total_chunks = total_vectors = 0
    for document in documents:
        total_chunks += reindex_document(session, client, document)
        total_vectors += reindex_document_vectors(session, client, document)
        total_documents += 1
    report.done.append(
        f"重建了三个索引：{total_documents} 个文档，{total_chunks} 个片段，"
        f"{total_vectors} 个图片向量"
    )


# ---- 数据库 ----


def _repair_db_chunks(session: Session, document_ids: Iterable[str], report: RepairReport) -> None:
    for raw_id in sorted(set(document_ids)):
        document = session.get(Document, uuid.UUID(raw_id), populate_existing=True)
        if document is None or document.deleted_at is not None:
            report.skipped.append(f"文档 {raw_id} 已删除，片段交给清理任务")
            continue
        if _busy(session, document.id):
            # parse 先写新版本的片段、最后才改 parse_version：这时删“非当前版本”会删掉新片段
            report.skipped.append(f"文档 {raw_id} 正在解析或识别，没有删除它的片段")
            continue
        condition = [DocumentChunk.document_id == document.id]
        if document.parse_version is not None:
            condition.append(DocumentChunk.parse_version != document.parse_version)
        result = session.execute(delete(DocumentChunk).where(*condition))
        session.commit()
        report.done.append(f"数据库：删除了文档 {raw_id} 的 {result.rowcount} 个旧版本片段")


def _repair_ocr_results(session: Session, result_ids: Iterable[str], report: RepairReport) -> None:
    deleted = 0
    for raw_id in sorted(set(result_ids)):
        result = session.get(OCRResult, uuid.UUID(raw_id))
        if result is None:
            continue
        if _busy(session, result.document_id):
            report.skipped.append(f"文档 {result.document_id} 正在解析或识别，没有删除识别结果")
            continue
        session.delete(result)
        deleted += 1
    session.commit()
    if deleted:
        report.done.append(f"数据库：删除了 {deleted} 条过期的识别结果")


def _repair_cleanup_tasks(
    session: Session, document_ids: Iterable[str], report: RepairReport
) -> None:
    for raw_id in sorted(set(document_ids)):
        document = session.get(Document, uuid.UUID(raw_id), populate_existing=True)
        pending = session.scalar(
            select(func.count())
            .select_from(ProcessingTask)
            .where(
                ProcessingTask.document_id == uuid.UUID(raw_id),
                ProcessingTask.task_type == TASK_CLEANUP,
                ProcessingTask.status.in_((STATUS_PENDING, STATUS_PROCESSING)),
            )
        )
        if document is None or document.deleted_at is None or pending:
            report.skipped.append(f"文档 {raw_id} 已不是“已删除未清理”的状态")
            continue
        session.add(ProcessingTask(task_type=TASK_CLEANUP, document_id=document.id))
        session.commit()
        report.done.append(f"任务：为文档 {raw_id} 补建了 cleanup 任务")


# ---- 磁盘 ----


def _repair_temp_files(root: Path, relatives: Iterable[str], report: RepairReport) -> None:
    tmp_dir = root.resolve() / TMP_DIR_NAME
    for relative in sorted(set(relatives)):
        path = root.resolve() / relative
        # 只删临时目录里直接的 .part 文件，不跟随符号链接
        if path.parent != tmp_dir or path.suffix != ".part" or path.is_symlink():
            report.skipped.append(f"{relative} 不是临时文件，没有删除")
            continue
        path.unlink(missing_ok=True)
        report.done.append(f"磁盘：删除了临时文件 {relative}")


def _repair_orphan_files(
    session: Session, storage: LocalStorage, keys: Iterable[str], report: RepairReport
) -> None:
    for key in sorted(set(keys)):
        referenced = session.scalar(
            select(func.count()).select_from(Document).where(Document.storage_key == key)
        )
        if referenced:
            report.skipped.append(f"{key} 在检查之后已经有了数据库记录，没有删除")
            continue
        storage.delete(key)
        report.done.append(f"磁盘：删除了没有记录的文件 {key}")


def _repair_embeddings(
    session: Session, embedding_ids: Iterable[str], report: RepairReport
) -> None:
    for raw_id in sorted(set(embedding_ids)):
        embedding_id = parse_uuid(raw_id)
        embedding = None if embedding_id is None else session.get(ImageEmbedding, embedding_id)
        if embedding is None:
            continue
        # 与 embed 任务用同一把锁：删除期间同内容的 embed 任务排队，删完后它会重新编码，
        # 而不是读到一条马上被删掉的向量、写进索引后留下对不上的数据
        lock_content(session, embedding.sha256)
        # 检查之后可能又上传了内容相同的图片：再查一次，还有引用就不删
        if session.scalar(
            select(func.count())
            .select_from(ImageAsset)
            .where(ImageAsset.sha256 == embedding.sha256)
        ):
            session.rollback()
            report.skipped.append(f"向量记录 {raw_id} 又被图片使用了，没有删除")
            continue
        session.delete(embedding)
        session.commit()
        report.done.append(f"数据库：删除了不再被使用的向量记录 {raw_id}")


# ---- 入口 ----


def apply(
    selected: Sequence[Issue],
    *,
    session: Session,
    client: OpenSearchClient | None,
    storage: LocalStorage,
    storage_root: Path,
) -> RepairReport:
    """执行修复。client 为 None（检索服务不可用）时，涉及索引的类别跳过并说明。"""
    report = RepairReport()
    by_kind: dict[str, list[Issue]] = {}
    for issue in selected:
        by_kind.setdefault(issue.repair or "", []).append(issue)

    def documents(kind: str) -> list[str]:
        return [i.document_id for i in by_kind.get(kind, []) if i.document_id]

    def targets(kind: str) -> list[str]:
        return [i.target for i in by_kind.get(kind, []) if i.target]

    _repair_db_chunks(session, documents(REPAIR_DB_CHUNKS), report)
    _repair_ocr_results(session, targets(REPAIR_OCR_RESULTS), report)
    _repair_cleanup_tasks(session, documents(REPAIR_CLEANUP_TASKS), report)

    rebuild = REPAIR_REBUILD_INDICES in by_kind
    if REPAIR_INDEX in by_kind or rebuild:
        if client is None:
            report.skipped.append("检索服务不可用，没有修复索引")
        elif rebuild:
            # 全部重建已经覆盖了单个文档的索引修复
            rebuild_indices(session, client, report)
        else:
            _repair_index(session, client, documents(REPAIR_INDEX), report)

    _repair_embeddings(session, targets(REPAIR_EMBEDDINGS), report)
    _repair_temp_files(storage_root, targets(REPAIR_TEMP_FILES), report)
    _repair_orphan_files(session, storage, targets(REPAIR_ORPHAN_FILES), report)
    return report
