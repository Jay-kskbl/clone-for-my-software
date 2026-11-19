"""一个 ocr 任务的处理（DEVPLAN T17）：

    1. 读出文档。不存在、已删除，或 payload 里的版本不是文档当前的版本 → 什么都不做，算成功
       （文档重新解析后，旧版本的 ocr 任务不会被删除，decisions.md D27）
    2. 识别子进程：渲染这一页（这张图片）并识别文字
    3. 切分成 source_type=ocr 的片段（与正文同一套规则、同一套参数）
    4. 数据库：换掉这个对象的识别结果和 OCR 片段（一个事务）
    4'. 第 4 步的事务里锁住文档行并复查：识别期间文档被删除或重新解析 → 什么都不写
    5. chunks 索引：删掉这个对象预留区间里的旧片段，写入新片段（不删别的版本）
    6. 再读一次文档：写完数据库后被删除 → 撤掉它在索引里的全部数据；
       被重新解析 → 只撤掉自己刚写的这一段

每一步都可以重复执行，结果不变：识别结果按“文档 + 对象”替换，片段 ID 是确定性的。

片段序号：OCR 片段与正文片段共用 {document_id}:{parse_version}:{seq} 的序号空间。
OCR 片段从 OCR_SEQ_BASE 开始，每个对象预留 OCR_SEQ_BLOCK 个：第 p 页的片段序号是
OCR_SEQ_BASE + (p-1) × OCR_SEQ_BLOCK 起，独立图片从 OCR_SEQ_BASE 起。
正文片段从 0 连续编号，远到不了 OCR_SEQ_BASE；数据库的 seq 是 32 位整数，上限约 21.4 亿。
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter, ValidationError
from shared.chunking import ChunkingParams, chunk_blocks
from shared.contracts import (
    Chunk,
    ImageLocator,
    OCRLine,
    OcrLocator,
    OCRResult,
    PdfPageLocator,
    Point,
    TextBlock,
)
from shared.storage_keys import InvalidStorageKeyError, resolve_storage_key
from shared.tasks import Task
from shared.text_index import (
    OpenSearchClient,
    delete_chunk_range,
    delete_document,
    ensure_indices,
    write_chunks,
)

from ocr_worker.engine_process import EngineProcess, EngineResult, Job
from ocr_worker.models import ModelInfo
from ocr_worker.store import Store

OCR_SEQ_BASE = 1_000_000_000
OCR_SEQ_BLOCK = 1000
_SEQ_LIMIT = 2**31 - 1
_LOCATOR = TypeAdapter(OcrLocator)


class OcrTaskError(Exception):
    """重试也不会成功的失败（任务参数不对、原始文件不见了、一页切出的片段过多）。"""

    retryable = False

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class Outcome:
    ok: bool
    error: str | None = None
    retryable: bool = True
    lease_lost: bool = False
    # 成功时说明做了什么：processed / skipped:<原因>
    note: str = ""


@dataclass(frozen=True)
class OcrOptions:
    dpi: int
    max_pixels: int
    min_confidence: float
    task_timeout_seconds: float
    heartbeat_seconds: float


def ocr_params(locator: OcrLocator, options: OcrOptions) -> dict[str, int | float | None]:
    """识别这个对象时实际起作用的参数，写进 ocr_results.params（T24c，decisions.md D42）。

    实验运行时读出来记进 config.json，并检查数据集里是否混用了不同的参数。
    pdf_dpi 只对 PDF 页起作用（渲染成图片的分辨率），独立图片不渲染，记为 None。
    min_confidence 不影响识别本身，只决定哪些行进入 OCR 片段；lines 里仍保存全部行。
    """
    return {
        "pdf_dpi": options.dpi if isinstance(locator, PdfPageLocator) else None,
        "min_confidence": options.min_confidence,
        "max_pixels": options.max_pixels,
    }


def seq_range(locator: OcrLocator) -> tuple[int, int]:
    """这个对象的 OCR 片段可以使用的序号区间 [start, end)。"""
    if isinstance(locator, PdfPageLocator):
        start = OCR_SEQ_BASE + (locator.page - 1) * OCR_SEQ_BLOCK
    else:
        start = OCR_SEQ_BASE
    end = start + OCR_SEQ_BLOCK
    if end > _SEQ_LIMIT:
        raise OcrTaskError(f"页码过大，超出片段序号的范围：{locator!r}")
    return start, end


def _parse_payload(task: Task) -> tuple[str, OcrLocator, ChunkingParams]:
    try:
        parse_version = str(task.payload["parse_version"])
        locator = _LOCATOR.validate_python(task.payload["locator"])
        chunking = task.payload["chunking"]
        params = ChunkingParams(
            max_chars=int(chunking["max_chars"]), overlap_chars=int(chunking["overlap_chars"])
        )
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise OcrTaskError(f"ocr 任务的参数不完整或格式不对（{type(exc).__name__}）") from exc
    if isinstance(locator, ImageLocator) and not locator.image_id.startswith(str(task.document_id)):
        raise OcrTaskError("ocr 任务的图片不属于这个文档")
    return parse_version, locator, params


def to_ocr_result(
    document_id: uuid.UUID,
    locator: OcrLocator,
    engine: EngineResult,
    model: ModelInfo,
    library_version: str,
) -> OCRResult:
    return OCRResult(
        document_id=document_id,
        locator=locator,
        lines=[
            OCRLine(
                text=line.text,
                bbox=tuple(Point(x=x, y=y) for x, y in line.bbox),  # type: ignore[arg-type]
                confidence=line.confidence,
            )
            for line in engine.lines
        ],
        model_name=model.model_name,
        model_version=model.model_version(library_version),
    )


def build_chunks(
    result: OCRResult,
    *,
    parse_version: str,
    params: ChunkingParams,
    min_confidence: float,
) -> list[Chunk]:
    """识别出的文字行 → OCR 片段。每行是一个文本块，定位都是这一页（这张图片），
    切分模块会把同一定位的相邻行合并成长度合适的片段。
    """
    start, end = seq_range(result.locator)
    # 一页（一张图片）的文字合成一个文本块，行与行之间换行，再按长度切分。
    # 不能一行一块：切分规则规定 PDF 页、图片定位的块互不合并（D25），那样每行都会
    # 单独成为一个片段，切分长度不起作用
    text = "\n".join(
        line.text.strip()
        for line in result.lines
        if line.confidence >= min_confidence and line.text.strip()
    )
    blocks = [TextBlock(text=text, locator=result.locator)] if text else []
    chunks = chunk_blocks(
        blocks,
        document_id=result.document_id,
        parse_version=parse_version,
        source_type="ocr",
        params=params,
        seq_start=start,
    )
    if chunks and chunks[-1].seq >= end:
        raise OcrTaskError(f"这一页切出的片段超过 {OCR_SEQ_BLOCK} 个，超出预留的序号区间")
    return chunks


def process_task(
    task: Task,
    *,
    store: Store,
    engine: EngineProcess,
    index: OpenSearchClient,
    model: ModelInfo,
    storage_root: Path,
    options: OcrOptions,
    on_tick: Callable[[], bool],
) -> Outcome:
    """处理一个 ocr 任务。预期中的失败返回 Outcome；数据库、检索服务的故障以异常抛出，
    由主循环按可重试的失败处理。
    """
    parse_version, locator, params = _parse_payload(task)

    document = store.document(task.document_id)
    if document is None or document.deleted:
        return Outcome(ok=True, note="skipped:document-deleted")
    if document.parse_version != parse_version:
        return Outcome(ok=True, note="skipped:stale-version")

    try:
        path = resolve_storage_key(storage_root, document.storage_key)
    except InvalidStorageKeyError as exc:
        raise OcrTaskError("文档的存储位置不合法，无法识别") from exc
    if not path.is_file():
        raise OcrTaskError("文档的原始文件不存在，无法识别")

    recognized = engine.run(
        Job(
            path=str(path),
            locator=locator.model_dump(mode="json"),
            dpi=options.dpi,
            max_pixels=options.max_pixels,
        ),
        timeout_seconds=options.task_timeout_seconds,
        tick_seconds=options.heartbeat_seconds,
        on_tick=on_tick,
    )
    if not recognized.ok:
        return Outcome(
            ok=False,
            error=recognized.error,
            retryable=recognized.retryable,
            lease_lost=recognized.lease_lost,
        )

    result = to_ocr_result(
        task.document_id, locator, recognized, model, engine.library_version or "unknown"
    )
    chunks = build_chunks(
        result, parse_version=parse_version, params=params, min_confidence=options.min_confidence
    )
    start, end = seq_range(locator)

    saved = store.save(
        result,
        chunks,
        parse_version=parse_version,
        seq_range=(start, end),
        params=ocr_params(locator, options),
    )
    if not saved:
        # 识别期间文档被删除或重新解析：识别结果作废，什么都不写
        return Outcome(ok=True, note="skipped:changed-during-ocr")

    ensure_indices(index)
    delete_chunk_range(
        index,
        document_id=task.document_id,
        parse_version=parse_version,
        seq_from=start,
        seq_to=end,
    )
    # 只写不删：不能用 index_document，它会删掉这个文档“其他版本”的片段
    write_chunks(index, chunks)

    document = store.document(task.document_id)
    if document is None or document.deleted:
        # 写完数据库之后文档被删除，清理任务可能已经先跑完：把它在索引里的数据全部撤掉
        delete_document(index, task.document_id)
        return Outcome(ok=True, note="skipped:deleted-during-ocr")
    if document.parse_version != parse_version:
        # 写完数据库之后文档被重新解析：只撤掉自己刚写的这一段，新版本的片段不动
        delete_chunk_range(
            index,
            document_id=task.document_id,
            parse_version=parse_version,
            seq_from=start,
            seq_to=end,
        )
        return Outcome(ok=True, note="skipped:reparsed-during-ocr")
    return Outcome(ok=True, note=f"processed:{len(result.lines)}-lines:{len(chunks)}-chunks")
