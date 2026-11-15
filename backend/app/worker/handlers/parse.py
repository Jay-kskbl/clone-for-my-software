"""parse 任务：解析 → 切分 → 写 DocumentChunk → 写索引 → 回写状态。

需要 OCR 的页和图片在最后创建 ocr 任务。

步骤与顺序（每一步都可以重复执行，结果不变）：

    1. 读出文档。记录已不存在或已被软删除 → 什么都不做，任务算成功。
    2. 文档状态改为 processing。
    3. 文件名和标签写入 doc_meta 索引。放在解析之前：即使正文解析失败，文件仍能按文件名搜到。
    4. 解析、切分（纯计算）。
    5. 数据库：换掉这个文档的正文片段；图片另外登记一条 ImageAsset。提交。
    6. chunks 索引：写入这一版的片段，同时清掉其他版本的。
    7. 再读一次文档。解析期间它被删除了 → 把刚写进索引的数据撤掉，结束。
    8. 数据库：状态改为 succeeded，记下 parse_version，创建 ocr 任务。提交。

状态 succeeded 最后才写，所以“成功”一定意味着数据库和索引里都已经有了正文片段。
中途任何一步失败都抛异常：任务由 Worker 记为失败并按规则重试，重试时从头再来。
文档状态何时变成 failed 不在这里处理：任务最终失败（不再重试）时由任务队列在同一个事务里
改写，见 shared/tasks.py 的 _mark_documents_failed。所以任务失败后等待重试的这段时间，
文档状态仍是 processing。

已知的窄窗口：第 7 步复查之后、第 8 步提交之前，文档恰好被 cleanup 任务硬删除时，
第 8 步会报错，第 6 步写进索引的片段会残留。检索时的数据库二次校验（附录 A10）保证
它们不会出现在结果里，一致性检查（T18）负责清掉。

文档状态只反映 parse 任务。OCR 任务的成败不改变文档状态（T17 如需调整再定）。
"""

import json
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from shared.chunking import ChunkingParams, chunk_document, make_parse_version
from shared.contracts import Chunk, OcrLocator, ParsedDocument
from shared.ids import make_image_id
from shared.tasks import STATUS_PROCESSING, STATUS_SUCCEEDED, TASK_OCR, Task
from shared.text_index import (
    OpenSearchClient,
    delete_document,
    ensure_indices,
    index_doc_meta,
    index_document,
)
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Document, DocumentChunk, ImageAsset, ProcessingTask
from app.modules.documents.tags import tags_by_document
from app.modules.parsing import (
    parse_docx,
    parse_image,
    parse_pdf,
    parse_xlsx,
    read_image_info,
)
from app.modules.storage import (
    InvalidStorageKeyError,
    LocalStorage,
    StoredFileNotFoundError,
)
from app.modules.storage.filetype import DOCX, JPEG, PDF, PNG, XLSX
from app.worker.context import task_context
from app.worker.handlers.errors import PipelineError

_IMAGE_MIME_TYPES = frozenset({PNG.mime_type, JPEG.mime_type})


def _live_document(session: Session, document_id: uuid.UUID) -> Document | None:
    """读出文档的最新状态；记录不存在或已软删除时返回 None。"""
    # populate_existing：会话里已经有这个对象时也用数据库里的最新值覆盖它
    document = session.get(Document, document_id, populate_existing=True)
    if document is None or document.deleted_at is not None:
        return None
    return document


def _parse_file(
    document: Document, path: Path, settings: Settings
) -> tuple[ParsedDocument, dict[str, int] | None]:
    """按文档的真实类型（上传时按文件内容识别的）选解析器。

    返回解析结果，以及会影响解析结果、因而要算进 parse_version 的解析参数。
    zip 和像素上限只决定“解析还是拒绝”，不改变解析出的内容，所以不算在内。
    """
    mime_type = document.mime_type
    if mime_type == PDF.mime_type:
        options = {"pdf_ocr_min_chars": settings.pdf_ocr_min_chars}
        return parse_pdf(path, ocr_min_chars=settings.pdf_ocr_min_chars), options
    if mime_type == DOCX.mime_type:
        return (
            parse_docx(
                path,
                zip_max_total_bytes=settings.parse_zip_max_total_bytes,
                zip_max_entries=settings.parse_zip_max_entries,
            ),
            None,
        )
    if mime_type == XLSX.mime_type:
        return (
            parse_xlsx(
                path,
                zip_max_total_bytes=settings.parse_zip_max_total_bytes,
                zip_max_entries=settings.parse_zip_max_entries,
            ),
            None,
        )
    if mime_type in _IMAGE_MIME_TYPES:
        return (
            parse_image(
                path,
                image_id=make_image_id(document.id),
                max_pixels=settings.parse_image_max_pixels,
            ),
            None,
        )
    raise PipelineError(f"不支持解析这种类型的文件：{mime_type}")


def _replace_body_chunks(
    session: Session, document_id: uuid.UUID, parse_version: str, chunks: Sequence[Chunk]
) -> None:
    """用这一批片段换掉文档现有的正文片段，并清掉其他版本的全部片段。

    同一版本的 OCR 片段保留：它们由 ocr 任务在之后写入，重新解析正文不应把它们删掉。
    """
    session.execute(
        delete(DocumentChunk).where(
            DocumentChunk.document_id == document_id,
            or_(
                DocumentChunk.parse_version != parse_version,
                DocumentChunk.source_type == "body",
            ),
        )
    )
    session.add_all(
        DocumentChunk(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            parse_version=chunk.parse_version,
            seq=chunk.seq,
            source_type=chunk.source_type,
            text=chunk.text,
            locator=chunk.locator.model_dump(mode="json"),
        )
        for chunk in chunks
    )


def _record_image_asset(
    session: Session, document: Document, path: Path, settings: Settings
) -> None:
    info = read_image_info(path, max_pixels=settings.parse_image_max_pixels)
    # merge：主键（image_id）已存在就更新，不存在就插入
    session.merge(
        ImageAsset(
            image_id=make_image_id(document.id),
            document_id=document.id,
            sha256=document.sha256,
            width=info.width,
            height=info.height,
        )
    )


def _ocr_payload(parse_version: str, target: OcrLocator, params: ChunkingParams) -> dict[str, Any]:
    """ocr 任务的参数。切分参数随任务一起交给 OCR Worker：OCR 片段必须与正文片段
    按同一套参数切分，parse_version 才名副其实；不能依赖 ocr 环境自己的配置恰好相同。
    """
    return {
        "parse_version": parse_version,
        "locator": target.model_dump(mode="json"),
        "chunking": {"max_chars": params.max_chars, "overlap_chars": params.overlap_chars},
    }


def _payload_key(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _create_ocr_tasks(
    session: Session,
    document_id: uuid.UUID,
    parse_version: str,
    targets: Sequence[OcrLocator],
    params: ChunkingParams,
) -> int:
    """每个需要 OCR 的页或图片一个任务。已经为同一版本的同一对象建过任务的不再建。

    一页一个任务，而不是一个文档一个任务：一页失败只重试这一页，
    一个上百页的扫描件也不会因为总耗时超过任务超时而整体失败。
    """
    existing = {
        _payload_key(payload)
        for payload in session.scalars(
            select(ProcessingTask.payload).where(
                ProcessingTask.document_id == document_id,
                ProcessingTask.task_type == TASK_OCR,
            )
        )
    }
    created = 0
    for target in targets:
        payload = _ocr_payload(parse_version, target, params)
        if _payload_key(payload) in existing:
            continue
        session.add(ProcessingTask(task_type=TASK_OCR, document_id=document_id, payload=payload))
        created += 1
    return created


def run_parse(
    task: Task,
    *,
    session: Session,
    storage: LocalStorage,
    index: OpenSearchClient,
    settings: Settings,
) -> None:
    """处理一个 parse 任务。资源由调用方提供，便于测试。"""
    document = _live_document(session, task.document_id)
    if document is None:
        # 文档在排队期间被删除了：没有东西可解析，清理由 cleanup 任务负责
        return

    document.status = STATUS_PROCESSING
    session.commit()

    # 索引不存在就建。放在这里而不是 Worker 启动时：检索服务比 Worker 晚启动也没关系
    ensure_indices(index)
    tags = tags_by_document(session, [document.id]).get(document.id, [])
    index_doc_meta(index, document_id=document.id, filename=document.filename, tags=tags)

    try:
        path = storage.local_path(document.storage_key)
    except (StoredFileNotFoundError, InvalidStorageKeyError) as exc:
        raise PipelineError("文档的原始文件不存在或无法读取，无法解析") from exc

    parsed, parser_options = _parse_file(document, path, settings)
    params = ChunkingParams(
        max_chars=settings.chunk_max_chars, overlap_chars=settings.chunk_overlap_chars
    )
    parse_version = make_parse_version(
        parser_name=parsed.parser_name,
        parser_version=parsed.parser_version,
        params=params,
        parser_options=parser_options,
    )
    chunks = chunk_document(
        parsed, document_id=document.id, parse_version=parse_version, params=params
    )

    _replace_body_chunks(session, document.id, parse_version, chunks)
    if document.mime_type in _IMAGE_MIME_TYPES:
        _record_image_asset(session, document, path, settings)
    session.commit()

    index_document(index, document_id=document.id, parse_version=parse_version, chunks=chunks)

    document = _live_document(session, task.document_id)
    if document is None:
        # 解析期间文档被删除，cleanup 任务可能已经先跑完了：把刚写进索引的数据撤掉
        delete_document(index, task.document_id)
        return

    document.status = STATUS_SUCCEEDED
    document.parse_version = parse_version
    _create_ocr_tasks(session, document.id, parse_version, parsed.ocr_targets, params)
    session.commit()


def handle_parse(task: Task) -> None:
    """parse 任务的入口（登记在 registry.HANDLERS，在子进程里执行）。"""
    with task_context() as ctx:
        run_parse(
            task,
            session=ctx.session,
            storage=ctx.storage,
            index=ctx.index,
            settings=ctx.settings,
        )
