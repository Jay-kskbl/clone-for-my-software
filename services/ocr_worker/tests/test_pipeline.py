"""T17：一个 ocr 任务的处理流程。数据库、识别子进程、检索服务都用假的代替。

对真实数据库的读写见 backend/tests/integration/test_ocr_worker_db.py。
"""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from shared.chunking import ChunkingParams
from shared.contracts import ImageLocator, OCRResult, PdfPageLocator
from shared.ids import parse_chunk_id
from shared.tasks import Task
from shared.text_index import OpenSearchClient

from ocr_worker.engine import RecognizedLine
from ocr_worker.engine_process import EngineResult
from ocr_worker.models import ModelInfo
from ocr_worker.pipeline import (
    OCR_SEQ_BASE,
    OCR_SEQ_BLOCK,
    OcrOptions,
    OcrTaskError,
    build_chunks,
    process_task,
    seq_range,
    to_ocr_result,
)
from ocr_worker.store import DocumentState

DOCUMENT_ID = uuid.UUID("11111111-2222-4333-8444-555555555555")
VERSION = "c1-m500-o50-aaaaaaaaaaaa"
KEY = f"2026/{DOCUMENT_ID}/{'0' * 64}.pdf"
BOX = ((0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0))
MODEL = ModelInfo(
    det_dir=Path("PP-OCRv5_mobile_det"),
    rec_dir=Path("PP-OCRv5_mobile_rec"),
    det_sha256="a" * 64,
    rec_sha256="b" * 64,
)
OPTIONS = OcrOptions(
    dpi=200, max_pixels=10**8, min_confidence=0.5, task_timeout_seconds=60, heartbeat_seconds=5
)


def line(text: str, confidence: float = 0.9) -> RecognizedLine:
    return RecognizedLine(text=text, confidence=confidence, bbox=BOX)


class FakeStore:
    def __init__(self, document: DocumentState | None, events: list) -> None:
        self.documents = [document]
        self.events = events
        self.saved: list[tuple[OCRResult, list, str, tuple[int, int]]] = []
        self.save_result = True

    def document(self, document_id):
        self.events.append(("db", "read"))
        return self.documents[0] if len(self.documents) == 1 else self.documents.pop(0)

    def save(self, result, chunks, *, parse_version, seq_range):
        self.events.append(("db", "save"))
        self.saved.append((result, list(chunks), parse_version, seq_range))
        return self.save_result


class FakeEngine:
    library_version = "3.7.0"

    def __init__(self, events: list, result: EngineResult) -> None:
        self.events = events
        self.result = result
        self.jobs = []

    def run(self, job, *, timeout_seconds, tick_seconds, on_tick=None):
        self.events.append(("engine", "run"))
        self.jobs.append((job, timeout_seconds, tick_seconds, on_tick))
        return self.result


class FakeIndex:
    def __init__(self, events: list) -> None:
        self.events = events
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.events.append(("index", f"{request.method} {request.url.path}"))
        return httpx.Response(200, json={})

    def client(self) -> OpenSearchClient:
        return OpenSearchClient(
            "http://search.test:9200",
            timeout_seconds=1.0,
            transport=httpx.MockTransport(self.handle),
        )


@pytest.fixture
def events() -> list:
    return []


@pytest.fixture
def storage_root(tmp_path) -> Path:
    path = tmp_path / "storage" / KEY
    path.parent.mkdir(parents=True)
    path.write_bytes(b"%PDF-1.7\n")
    return tmp_path / "storage"


def live(parse_version: str | None = VERSION, deleted: bool = False) -> DocumentState:
    return DocumentState(
        parse_version=parse_version,
        deleted_at=datetime.now(UTC) if deleted else None,
        storage_key=KEY,
        mime_type="application/pdf",
    )


def task(locator: dict | None = None, **payload) -> Task:
    body = {
        "parse_version": VERSION,
        "locator": locator or {"type": "pdf_page", "page": 3},
        "chunking": {"max_chars": 500, "overlap_chars": 50},
        **payload,
    }
    return Task(
        id=uuid.uuid4(),
        task_type="ocr",
        document_id=DOCUMENT_ID,
        payload=body,
        attempts=1,
        max_attempts=3,
    )


def run(events, storage_root, *, document=None, engine_result=None, the_task=None):
    store = FakeStore(document if document is not None else live(), events)
    engine = FakeEngine(
        events, engine_result or EngineResult(ok=True, lines=(line("第一行"), line("第二行")))
    )
    index = FakeIndex(events)
    outcome = process_task(
        the_task or task(),
        store=store,
        engine=engine,
        index=index.client(),
        model=MODEL,
        storage_root=storage_root,
        options=OPTIONS,
        on_tick=lambda: True,
    )
    return outcome, store, engine, index


# ---- 正常流程 ----


def test_page_is_recognized_saved_and_indexed_in_order(events, storage_root):
    outcome, store, engine, _ = run(events, storage_root)

    assert outcome.ok
    start = OCR_SEQ_BASE + 2 * OCR_SEQ_BLOCK
    assert events == [
        ("db", "read"),
        ("engine", "run"),
        ("db", "save"),
        ("index", "HEAD /doc_meta"),
        ("index", "HEAD /chunks"),
        ("index", "POST /chunks/_delete_by_query"),  # 这一页预留区间里的旧片段
        ("index", "POST /_bulk"),
        ("db", "read"),  # 复查是否被删除
    ]
    (result, chunks, version, saved_range) = store.saved[0]
    assert (version, saved_range) == (VERSION, (start, start + OCR_SEQ_BLOCK))
    assert [c.seq for c in chunks] == [start]
    assert chunks[0].text == "第一行\n第二行"
    assert chunks[0].source_type == "ocr"
    assert chunks[0].locator == PdfPageLocator(page=3)
    assert parse_chunk_id(chunks[0].chunk_id) == (DOCUMENT_ID, VERSION, start)
    # 识别结果记录了模型名称和带哈希的版本
    assert result.model_name == "PP-OCRv5_mobile_det+PP-OCRv5_mobile_rec"
    assert result.model_version == "paddleocr-3.7.0/det-aaaaaaaa/rec-bbbbbbbb"


def test_job_carries_the_file_path_locator_and_options(events, storage_root):
    _, _, engine, _ = run(events, storage_root)

    job, timeout, tick, on_tick = engine.jobs[0]
    assert Path(job.path) == storage_root / KEY
    assert job.locator == {"type": "pdf_page", "page": 3}
    assert (job.dpi, job.max_pixels, timeout, tick) == (200, 10**8, 60, 5)
    assert on_tick() is True


def test_the_range_delete_targets_only_this_page(events, storage_root):
    _, _, _, index = run(events, storage_root)

    body = json.loads(index.requests[2].content)
    start = OCR_SEQ_BASE + 2 * OCR_SEQ_BLOCK
    assert body["query"]["bool"]["filter"] == [
        {"term": {"document_id": str(DOCUMENT_ID)}},
        {"term": {"parse_version": VERSION}},
        {"range": {"seq": {"gte": start, "lt": start + OCR_SEQ_BLOCK}}},
    ]


def test_low_confidence_lines_are_saved_but_not_searchable(events, storage_root):
    engine_result = EngineResult(ok=True, lines=(line("清楚", 0.9), line("模糊", 0.2)))

    _, store, _, _ = run(events, storage_root, engine_result=engine_result)

    result, chunks, _, _ = store.saved[0]
    assert [x.text for x in result.lines] == ["清楚", "模糊"]
    assert [c.text for c in chunks] == ["清楚"]


def test_page_without_text_saves_an_empty_result_and_no_chunks(events, storage_root):
    outcome, store, _, index = run(events, storage_root, engine_result=EngineResult(ok=True))

    assert outcome.ok
    result, chunks, _, _ = store.saved[0]
    assert result.lines == [] and chunks == []
    # 仍然清掉这一页以前的片段；没有新片段可写
    assert "POST /_bulk" not in [f"{r.method} {r.url.path}" for r in index.requests]


def test_image_task_uses_the_image_block(events, storage_root):
    the_task = task({"type": "image", "image_id": str(DOCUMENT_ID)})

    _, store, _, _ = run(events, storage_root, the_task=the_task)

    _, chunks, _, saved_range = store.saved[0]
    assert saved_range == (OCR_SEQ_BASE, OCR_SEQ_BASE + OCR_SEQ_BLOCK)
    assert chunks[0].locator == ImageLocator(image_id=str(DOCUMENT_ID))


# ---- 跳过 ----


@pytest.mark.parametrize(
    "document, note",
    [
        (live(deleted=True), "skipped:document-deleted"),
        (live(parse_version="c1-m300-o50-bbbbbbbbbbbb"), "skipped:stale-version"),
        (live(parse_version=None), "skipped:stale-version"),
    ],
)
def test_deleted_or_reparsed_documents_are_skipped_without_ocr(
    events, storage_root, document, note
):
    outcome, store, _, _ = run(events, storage_root, document=document)

    assert outcome.ok and outcome.note == note
    assert events == [("db", "read")]
    assert store.saved == []


def test_missing_document_record_is_skipped(events, storage_root):
    store = FakeStore(None, events)
    outcome = process_task(
        task(),
        store=store,
        engine=FakeEngine(events, EngineResult(ok=True)),
        index=FakeIndex(events).client(),
        model=MODEL,
        storage_root=storage_root,
        options=OPTIONS,
        on_tick=lambda: True,
    )

    assert outcome.ok and outcome.note == "skipped:document-deleted"


def test_document_deleted_during_ocr_has_its_index_data_withdrawn(events, storage_root):
    store = FakeStore(live(), events)
    store.documents = [live(), live(deleted=True)]
    index = FakeIndex(events)

    outcome = process_task(
        task(),
        store=store,
        engine=FakeEngine(events, EngineResult(ok=True, lines=(line("文字"),))),
        index=index.client(),
        model=MODEL,
        storage_root=storage_root,
        options=OPTIONS,
        on_tick=lambda: True,
    )

    assert outcome.note == "skipped:deleted-during-ocr"
    assert events[-2:] == [
        ("index", "POST /chunks/_delete_by_query"),
        ("index", f"DELETE /doc_meta/_doc/{DOCUMENT_ID}"),
    ]


# ---- 失败 ----


def test_engine_failure_is_passed_through_and_nothing_is_written(events, storage_root):
    failure = EngineResult(ok=False, error="识别超时（超过 60 秒），已终止", retryable=True)

    outcome, store, _, index = run(events, storage_root, engine_result=failure)

    assert (outcome.ok, outcome.retryable, outcome.error) == (False, True, failure.error)
    assert store.saved == [] and index.requests == []


def test_lost_lease_is_passed_through(events, storage_root):
    lost = EngineResult(ok=False, error="租约已丢失", lease_lost=True)

    outcome, store, _, _ = run(events, storage_root, engine_result=lost)

    assert outcome.lease_lost and store.saved == []


def test_missing_file_on_disk_is_not_retryable(events, tmp_path):
    with pytest.raises(OcrTaskError, match="原始文件不存在"):
        run(events, tmp_path / "empty-storage")


@pytest.mark.parametrize(
    "payload",
    [
        {"parse_version": VERSION, "locator": {"type": "pdf_page", "page": 1}},  # 没有 chunking
        {"parse_version": VERSION, "chunking": {"max_chars": 500, "overlap_chars": 50}},
        {
            "parse_version": VERSION,
            "locator": {"type": "docx_para", "para_index": 0},  # 不是 OCR 对象
            "chunking": {"max_chars": 500, "overlap_chars": 50},
        },
        {
            "parse_version": VERSION,
            "locator": {"type": "image", "image_id": str(uuid.uuid4())},  # 别的文档的图片
            "chunking": {"max_chars": 500, "overlap_chars": 50},
        },
    ],
)
def test_malformed_payload_is_not_retryable(events, storage_root, payload):
    bad = Task(
        id=uuid.uuid4(),
        task_type="ocr",
        document_id=DOCUMENT_ID,
        payload=payload,
        attempts=1,
        max_attempts=3,
    )

    with pytest.raises(OcrTaskError) as excinfo:
        run(events, storage_root, the_task=bad)

    assert excinfo.value.retryable is False
    assert events == []


def test_search_service_failure_propagates_for_retry(events, storage_root):
    store = FakeStore(live(), events)

    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    index = OpenSearchClient(
        "http://search.test:9200", timeout_seconds=1.0, transport=httpx.MockTransport(refuse)
    )
    from shared.text_index import TextIndexUnavailable

    with pytest.raises(TextIndexUnavailable):
        process_task(
            task(),
            store=store,
            engine=FakeEngine(events, EngineResult(ok=True, lines=(line("文字"),))),
            index=index,
            model=MODEL,
            storage_root=storage_root,
            options=OPTIONS,
            on_tick=lambda: True,
        )


# ---- 序号区间与切分 ----


def test_seq_ranges_of_different_pages_never_overlap():
    ranges = [seq_range(PdfPageLocator(page=p)) for p in range(1, 50)]

    for (_, end), (next_start, _) in zip(ranges, ranges[1:], strict=False):
        assert end == next_start
    assert ranges[0][0] == OCR_SEQ_BASE


def test_seq_range_stays_inside_a_32_bit_integer():
    with pytest.raises(OcrTaskError):
        seq_range(PdfPageLocator(page=2_000_000))
    start, end = seq_range(PdfPageLocator(page=1_000_000))
    assert end <= 2**31 - 1


def test_too_many_chunks_for_one_page_is_an_error():
    # 每行 50 个字、切分长度 50：一行至少一个片段，行数比预留的区间多
    lines = tuple(line("字" * 50) for _ in range(OCR_SEQ_BLOCK + 100))
    result = to_ocr_result(
        DOCUMENT_ID, PdfPageLocator(page=1), EngineResult(ok=True, lines=lines), MODEL, "3.7.0"
    )

    with pytest.raises(OcrTaskError, match="超出预留"):
        build_chunks(
            result,
            parse_version=VERSION,
            params=ChunkingParams(max_chars=50, overlap_chars=0),
            min_confidence=0.0,
        )


def test_chunking_is_deterministic_and_respects_the_given_parameters():
    lines = tuple(line("字" * 30) for _ in range(5))
    result = to_ocr_result(
        DOCUMENT_ID, PdfPageLocator(page=1), EngineResult(ok=True, lines=lines), MODEL, "3.7.0"
    )

    def chunks(max_chars):
        return build_chunks(
            result,
            parse_version=VERSION,
            params=ChunkingParams(max_chars=max_chars, overlap_chars=0),
            min_confidence=0.0,
        )

    assert chunks(100) == chunks(100)
    assert len(chunks(100)) < len(chunks(50))
    assert all(len(c.text) <= 50 for c in chunks(50))


def test_document_changed_during_ocr_writes_nothing(events, storage_root):
    store = FakeStore(live(), events)
    store.save_result = False  # 保存时的复查发现文档已被删除或重新解析
    index = FakeIndex(events)

    outcome = process_task(
        task(),
        store=store,
        engine=FakeEngine(events, EngineResult(ok=True, lines=(line("文字"),))),
        index=index.client(),
        model=MODEL,
        storage_root=storage_root,
        options=OPTIONS,
        on_tick=lambda: True,
    )

    assert outcome.ok and outcome.note == "skipped:changed-during-ocr"
    assert index.requests == []


def test_reparse_after_saving_withdraws_only_this_range(events, storage_root):
    store = FakeStore(live(), events)
    store.documents = [live(), live(parse_version="c1-m300-o50-bbbbbbbbbbbb")]
    index = FakeIndex(events)

    outcome = process_task(
        task(),
        store=store,
        engine=FakeEngine(events, EngineResult(ok=True, lines=(line("文字"),))),
        index=index.client(),
        model=MODEL,
        storage_root=storage_root,
        options=OPTIONS,
        on_tick=lambda: True,
    )

    assert outcome.note == "skipped:reparsed-during-ocr"
    last = index.requests[-1]
    assert last.url.path == "/chunks/_delete_by_query"
    # 只删旧版本里自己这一页的区间，新版本的片段不受影响
    filters = json.loads(last.content)["query"]["bool"]["filter"]
    assert {"term": {"parse_version": VERSION}} in filters
    assert any("range" in f for f in filters)


def test_ocr_never_deletes_other_versions_from_the_index(events, storage_root):
    _, _, _, index = run(events, storage_root)

    for request in index.requests:
        if request.url.path.endswith("_delete_by_query"):
            assert "must_not" not in json.loads(request.content)["query"]["bool"]
