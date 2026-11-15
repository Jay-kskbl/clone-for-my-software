"""T14：解析流水线（parse、cleanup 两个任务处理函数）。本文件不需要数据库和 OpenSearch。

文件存储是真的（临时目录），解析和切分是真的；数据库会话和检索服务是假的，
它们把收到的操作按先后记在同一个事件列表里，用来检查步骤的顺序。

DEVPLAN 要求的端到端测试（上传 PDF → 等任务完成 → chunks 索引中有数据）需要
PostgreSQL 和 OpenSearch，见 tests/integration/test_pipeline_db.py。
"""

import io
import json
import pickle
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import docx
import httpx
import openpyxl
import pymupdf
import pytest
from shared.chunking import ChunkingParams, make_parse_version
from shared.tasks import TASK_CLEANUP, TASK_OCR, TASK_PARSE, Task
from shared.text_index import OpenSearchClient, TextIndexUnavailable

from app.db.models import Document, DocumentChunk, ImageAsset, ProcessingTask
from app.modules.parsing import ParseError
from app.modules.storage import LocalStorage
from app.modules.storage.filetype import DOCX, JPEG, PDF, PNG, XLSX
from app.worker import registry
from app.worker.handlers import (
    PipelineError,
    handle_cleanup,
    handle_parse,
    run_cleanup,
    run_parse,
)
from app.worker.handlers import parse as parse_module

SETTINGS = SimpleNamespace(
    pdf_ocr_min_chars=20,
    parse_zip_max_total_bytes=50 * 1024 * 1024,
    parse_zip_max_entries=1000,
    parse_image_max_pixels=10_000_000,
    chunk_max_chars=500,
    chunk_overlap_chars=50,
)

PAGE_TEXT = "智能文档管理系统的设计目标是让扫描件和图片中的文字也能被检索。"


# ---- 假的数据库会话与检索服务 ----


class FakeSession:
    """只实现处理函数用到的那几个方法，并把操作记进 events。"""

    def __init__(self, events: list, *documents: Document) -> None:
        self.events = events
        self.documents = {d.id: d for d in documents}
        self.added: list = []
        self.merged: list = []
        # 数据库里已有的 ocr 任务的 payload（用来测“不重复建任务”）
        self.existing_ocr_payloads: list[dict] = []
        # 第 n 次读取文档之前要做的事（用来模拟“解析期间文档被删除”）
        self.before_get: dict[int, object] = {}
        self._gets = 0

    def get(self, model, key, populate_existing=False):
        assert model is Document
        self._gets += 1
        hook = self.before_get.get(self._gets)
        if hook:
            hook()
        return self.documents.get(key)

    def execute(self, statement):
        table = statement.table.name
        self.events.append(("db", f"delete:{table}"))
        if table == "documents":
            self.documents.clear()

    def scalars(self, statement):
        return list(self.existing_ocr_payloads)

    def add(self, obj) -> None:
        self.added.append(obj)

    def add_all(self, objs) -> None:
        self.added.extend(objs)

    def merge(self, obj) -> None:
        self.merged.append(obj)

    def commit(self) -> None:
        statuses = sorted(d.status for d in self.documents.values())
        self.events.append(("db", f"commit:{','.join(statuses)}"))

    def of_type(self, cls) -> list:
        return [obj for obj in self.added if isinstance(obj, cls)]


class FakeIndex:
    def __init__(self, events: list) -> None:
        self.events = events
        self.requests: list[httpx.Request] = []
        self.down = False

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("refused", request=request)
        self.requests.append(request)
        self.events.append(("index", f"{request.method} {request.url.path}"))
        return httpx.Response(200, json={})

    def client(self) -> OpenSearchClient:
        return OpenSearchClient(
            "http://search.test:9200",
            timeout_seconds=1.0,
            transport=httpx.MockTransport(self.handle),
        )

    def paths(self) -> list[str]:
        return [f"{r.method} {r.url.path}" for r in self.requests]

    def bulk_chunk_ids(self) -> list[str]:
        ids: list[str] = []
        for request in self.requests:
            if request.url.path == "/_bulk":
                lines = request.content.decode("utf-8").splitlines()
                ids.extend(json.loads(line)["index"]["_id"] for line in lines[0::2])
        return ids


@pytest.fixture
def events() -> list:
    return []


@pytest.fixture
def index(events) -> FakeIndex:
    return FakeIndex(events)


@pytest.fixture
def storage(tmp_path) -> LocalStorage:
    return LocalStorage(tmp_path / "storage")


@pytest.fixture(autouse=True)
def no_tags(monkeypatch):
    """标签查询要用真实的数据库；这里固定返回两个标签。"""
    monkeypatch.setattr(
        parse_module,
        "tags_by_document",
        lambda session, ids: {document_id: ["合同", "财务"] for document_id in ids},
    )


# ---- 造文件 ----


def text_pdf(pages: int = 2) -> bytes:
    doc = pymupdf.open()
    for number in range(pages):
        page = doc.new_page()
        page.insert_textbox(
            pymupdf.Rect(50, 50, 550, 300),
            f"第{number + 1}页。{PAGE_TEXT}",
            fontname="china-s",
            fontsize=12,
        )
    data = doc.tobytes()
    doc.close()
    return data


def scanned_pdf(pages: int = 3) -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 100))
        pixmap.clear_with(200)
        page.insert_image(pymupdf.Rect(50, 50, 450, 250), pixmap=pixmap)
    data = doc.tobytes()
    doc.close()
    return data


def png_image(width: int = 320, height: int = 200) -> bytes:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height))
    pixmap.clear_with(180)
    return pixmap.tobytes("png")


def word_file() -> bytes:
    document = docx.Document()
    document.add_paragraph("第一段：系统支持 Word 文档。")
    document.add_paragraph("第二段：定位到段落。")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def excel_file() -> bytes:
    workbook = openpyxl.Workbook()
    workbook.active.title = "成绩"
    workbook.active.append(["姓名", "分数"])
    workbook.active.append(["张三", 95])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def stored_document(storage: LocalStorage, data: bytes, mime_type: str, name: str) -> Document:
    document_id = uuid.uuid4()
    stored = storage.put(io.BytesIO(data), document_id=document_id)
    return Document(
        id=document_id,
        owner_id=uuid.uuid4(),
        filename=name,
        mime_type=mime_type,
        size_bytes=len(data),
        sha256=stored.sha256,
        storage_key=stored.storage_key,
        status="pending",
    )


def task_for(document: Document, task_type: str = TASK_PARSE) -> Task:
    return Task(
        id=uuid.uuid4(),
        task_type=task_type,
        document_id=document.id,
        payload={},
        attempts=1,
        max_attempts=3,
    )


def parse(document, session, storage, index) -> None:
    run_parse(
        task_for(document),
        session=session,
        storage=storage,
        index=index.client(),
        settings=SETTINGS,
    )


def file_path(storage: LocalStorage, document: Document) -> Path:
    return storage.local_path(document.storage_key)


# ---- parse：有文本层的 PDF ----


def test_text_pdf_is_parsed_chunked_stored_and_indexed(events, index, storage):
    document = stored_document(storage, text_pdf(2), PDF.mime_type, "设计说明.pdf")
    session = FakeSession(events, document)

    parse(document, session, storage, index)

    chunks = session.of_type(DocumentChunk)
    assert [c.locator for c in chunks] == [
        {"type": "pdf_page", "page": 1},
        {"type": "pdf_page", "page": 2},
    ]
    assert all(c.source_type == "body" and c.document_id == document.id for c in chunks)
    assert PAGE_TEXT[:10] in "".join(chunks[0].text.split())
    # 写进索引的片段与写进数据库的是同一批
    assert index.bulk_chunk_ids() == [c.chunk_id for c in chunks]
    assert document.status == "succeeded"
    assert document.parse_version == chunks[0].parse_version
    assert session.of_type(ProcessingTask) == []


def test_parse_version_reflects_parser_and_chunking_parameters(events, index, storage):
    document = stored_document(storage, text_pdf(1), PDF.mime_type, "a.pdf")

    parse(document, FakeSession(events, document), storage, index)

    assert document.parse_version == make_parse_version(
        parser_name="pymupdf",
        parser_version=pymupdf.__version__,
        params=ChunkingParams(max_chars=500, overlap_chars=50),
        parser_options={"pdf_ocr_min_chars": 20},
    )


def test_steps_happen_in_the_documented_order(events, index, storage):
    document = stored_document(storage, text_pdf(1), PDF.mime_type, "a.pdf")

    parse(document, FakeSession(events, document), storage, index)

    assert events == [
        ("db", "commit:processing"),
        ("index", "HEAD /doc_meta"),
        ("index", "HEAD /chunks"),
        # 文件名和标签先进索引：正文解析失败也能按文件名搜到
        ("index", f"PUT /doc_meta/_doc/{document.id}"),
        ("db", "delete:document_chunks"),
        ("db", "commit:processing"),
        ("index", "POST /chunks/_delete_by_query"),
        ("index", "POST /_bulk"),
        # “成功”最后才写：此时数据库和索引里都已经有了片段
        ("db", "commit:succeeded"),
    ]


def test_file_name_and_tags_go_to_doc_meta(events, index, storage):
    document = stored_document(storage, text_pdf(1), PDF.mime_type, "年度报告.pdf")

    parse(document, FakeSession(events, document), storage, index)

    request = next(r for r in index.requests if r.method == "PUT")
    assert json.loads(request.content) == {
        "document_id": str(document.id),
        "filename": "年度报告.pdf",
        "tags": ["合同", "财务"],
    }


def test_running_the_same_parse_twice_gives_the_same_chunks(events, index, storage):
    document = stored_document(storage, text_pdf(2), PDF.mime_type, "a.pdf")
    first, second = FakeSession(events, document), FakeSession(events, document)

    parse(document, first, storage, index)
    parse(document, second, storage, index)

    def summary(session):
        return [(c.chunk_id, c.text) for c in session.of_type(DocumentChunk)]

    # 确定性 ID：第二次写入的每一条都与第一次同主键，是覆盖而不是追加
    assert summary(first) == summary(second)
    # 每次都先清掉旧的正文片段再写
    assert events.count(("db", "delete:document_chunks")) == 2


# ---- parse：需要 OCR 的内容 ----


def test_scanned_pdf_creates_one_ocr_task_per_page_and_no_chunks(events, index, storage):
    document = stored_document(storage, scanned_pdf(3), PDF.mime_type, "扫描件.pdf")
    session = FakeSession(events, document)

    parse(document, session, storage, index)

    assert session.of_type(DocumentChunk) == []
    tasks = session.of_type(ProcessingTask)
    assert [t.task_type for t in tasks] == [TASK_OCR] * 3
    assert all(t.document_id == document.id for t in tasks)
    assert [t.payload for t in tasks] == [
        {
            "parse_version": document.parse_version,
            "locator": {"type": "pdf_page", "page": n},
            "chunking": {"max_chars": 500, "overlap_chars": 50},
        }
        for n in (1, 2, 3)
    ]
    # 没有正文片段时不发批量写入，但仍要清掉这个文档其他版本的旧片段
    assert "POST /_bulk" not in index.paths()
    assert "POST /chunks/_delete_by_query" in index.paths()
    # 文档状态只反映 parse 任务：解析本身成功了
    assert document.status == "succeeded"


def test_ocr_tasks_are_not_created_twice_for_the_same_version(events, index, storage):
    document = stored_document(storage, scanned_pdf(3), PDF.mime_type, "扫描件.pdf")
    first = FakeSession(events, document)
    parse(document, first, storage, index)
    already = [t.payload for t in first.of_type(ProcessingTask)]

    # 同一个 parse 任务被重复执行（例如回写结果前 Worker 崩溃）；其中一页的任务此前没建成
    second = FakeSession(events, document)
    second.existing_ocr_payloads = already[:2]
    parse(document, second, storage, index)

    assert [t.payload for t in second.of_type(ProcessingTask)] == already[2:]


def test_ocr_tasks_are_created_only_together_with_success(events, index, storage):
    document = stored_document(storage, scanned_pdf(1), PDF.mime_type, "扫描件.pdf")
    session = FakeSession(events, document)
    index.down = True

    with pytest.raises(TextIndexUnavailable):
        parse(document, session, storage, index)

    assert session.of_type(ProcessingTask) == []


def test_image_is_recorded_and_handed_to_ocr(events, index, storage):
    document = stored_document(storage, png_image(320, 200), PNG.mime_type, "照片.png")
    session = FakeSession(events, document)

    parse(document, session, storage, index)

    (asset,) = session.merged
    assert isinstance(asset, ImageAsset)
    assert (asset.image_id, asset.document_id) == (str(document.id), document.id)
    assert (asset.width, asset.height, asset.sha256) == (320, 200, document.sha256)
    (ocr,) = session.of_type(ProcessingTask)
    assert ocr.payload["locator"] == {"type": "image", "image_id": str(document.id)}
    assert session.of_type(DocumentChunk) == []
    assert document.status == "succeeded"


def test_non_image_documents_get_no_image_asset(events, index, storage):
    document = stored_document(storage, text_pdf(1), PDF.mime_type, "a.pdf")
    session = FakeSession(events, document)

    parse(document, session, storage, index)

    assert session.merged == []


# ---- parse：Word 与 Excel ----


def test_word_document_goes_through_the_docx_parser(events, index, storage):
    document = stored_document(storage, word_file(), DOCX.mime_type, "说明.docx")
    session = FakeSession(events, document)

    parse(document, session, storage, index)

    (chunk,) = session.of_type(DocumentChunk)
    assert chunk.locator == {"type": "docx_para", "para_index": 0}
    assert "第一段" in chunk.text and "第二段" in chunk.text
    assert document.parse_version == make_parse_version(
        parser_name="python-docx",
        parser_version=docx.__version__,
        params=ChunkingParams(max_chars=500, overlap_chars=50),
        parser_options=None,
    )


def test_excel_workbook_goes_through_the_xlsx_parser(events, index, storage):
    document = stored_document(storage, excel_file(), XLSX.mime_type, "成绩.xlsx")
    session = FakeSession(events, document)

    parse(document, session, storage, index)

    (chunk,) = session.of_type(DocumentChunk)
    assert chunk.locator == {"type": "xlsx_range", "sheet": "成绩", "range": "A1:B2"}
    assert chunk.text == "姓名\t分数\n张三\t95"


def test_parser_is_chosen_by_recorded_type_not_by_file_name(events, index, storage):
    # 文件名是 .docx，内容和记录的类型是 PDF：按 PDF 解析
    document = stored_document(storage, text_pdf(1), PDF.mime_type, "其实是pdf.docx")
    session = FakeSession(events, document)

    parse(document, session, storage, index)

    assert session.of_type(DocumentChunk)[0].locator == {"type": "pdf_page", "page": 1}


def test_jpeg_mime_type_is_treated_as_image(events, index, storage, monkeypatch):
    document = stored_document(storage, png_image(), PNG.mime_type, "a.png")
    # 存储按内容识别成了 PNG；这里只验证 JPEG 的类型名也走图片分支
    document.mime_type = JPEG.mime_type
    session = FakeSession(events, document)

    parse(document, session, storage, index)

    assert len(session.merged) == 1


# ---- parse：文档被删除 ----


def test_soft_deleted_document_is_skipped_entirely(events, index, storage):
    document = stored_document(storage, text_pdf(1), PDF.mime_type, "a.pdf")
    document.deleted_at = datetime.now(UTC)
    session = FakeSession(events, document)

    parse(document, session, storage, index)

    # 任务正常结束（算成功），但什么都没做
    assert events == []
    assert document.status == "pending"


def test_missing_document_record_is_skipped(events, index, storage):
    document = stored_document(storage, text_pdf(1), PDF.mime_type, "a.pdf")

    parse(document, FakeSession(events), storage, index)

    assert events == []


def test_document_deleted_while_parsing_has_its_index_data_withdrawn(events, index, storage):
    document = stored_document(storage, text_pdf(1), PDF.mime_type, "a.pdf")
    session = FakeSession(events, document)

    def delete_now() -> None:
        document.deleted_at = datetime.now(UTC)

    # 第二次读取文档（写完索引之后的复查）之前，用户把它删了
    session.before_get[2] = delete_now

    parse(document, session, storage, index)

    bulk = events.index(("index", "POST /_bulk"))
    assert events[bulk + 1 :] == [
        ("index", "POST /chunks/_delete_by_query"),
        ("index", f"DELETE /doc_meta/_doc/{document.id}"),
    ]
    assert document.status == "processing"
    assert document.parse_version is None
    assert session.of_type(ProcessingTask) == []


def test_document_hard_deleted_while_parsing_is_handled_the_same_way(events, index, storage):
    document = stored_document(storage, text_pdf(1), PDF.mime_type, "a.pdf")
    session = FakeSession(events, document)
    session.before_get[2] = session.documents.clear

    parse(document, session, storage, index)

    assert events[-1] == ("index", f"DELETE /doc_meta/_doc/{document.id}")


# ---- parse：失败 ----


def test_corrupt_file_fails_without_retry_and_leaves_no_chunks(events, index, storage):
    document = stored_document(
        storage, b"%PDF-1.7\nthis is not really a pdf", PDF.mime_type, "坏文件.pdf"
    )
    session = FakeSession(events, document)

    with pytest.raises(ParseError) as excinfo:
        parse(document, session, storage, index)

    assert excinfo.value.retryable is False
    assert session.added == []
    assert "POST /_bulk" not in index.paths()
    # 文件名已经进了索引：解析失败的文件仍能按文件名找到
    assert f"PUT /doc_meta/_doc/{document.id}" in index.paths()
    # 处理函数不负责把文档标成 failed：那是任务队列在任务最终失败时做的
    assert document.status == "processing"


def test_missing_file_on_disk_fails_without_retry(events, index, storage):
    document = stored_document(storage, text_pdf(1), PDF.mime_type, "a.pdf")
    storage.delete(document.storage_key)
    session = FakeSession(events, document)

    with pytest.raises(PipelineError, match="原始文件") as excinfo:
        parse(document, session, storage, index)

    assert excinfo.value.retryable is False
    assert str(storage.local_path.__self__) not in excinfo.value.message
    assert document.storage_key not in excinfo.value.message


def test_unknown_mime_type_fails_without_retry(events, index, storage):
    document = stored_document(storage, text_pdf(1), PDF.mime_type, "a.pdf")
    document.mime_type = "application/zip"

    with pytest.raises(PipelineError, match="不支持") as excinfo:
        parse(document, FakeSession(events, document), storage, index)

    assert excinfo.value.retryable is False


def test_search_service_down_is_a_retryable_failure_and_not_success(events, index, storage):
    document = stored_document(storage, text_pdf(1), PDF.mime_type, "a.pdf")
    session = FakeSession(events, document)
    index.down = True

    with pytest.raises(TextIndexUnavailable) as excinfo:
        parse(document, session, storage, index)

    assert excinfo.value.retryable is True
    assert document.status == "processing"
    assert document.parse_version is None


# ---- cleanup ----


def cleanup(document, session, storage, index) -> None:
    run_cleanup(
        task_for(document, TASK_CLEANUP), session=session, storage=storage, index=index.client()
    )


def deleted_document(storage: LocalStorage) -> Document:
    document = stored_document(storage, text_pdf(1), PDF.mime_type, "a.pdf")
    document.deleted_at = datetime.now(UTC)
    return document


def test_cleanup_removes_index_data_then_file_then_record(events, index, storage):
    document = deleted_document(storage)
    path = file_path(storage, document)
    session = FakeSession(events, document)

    cleanup(document, session, storage, index)

    assert events == [
        ("index", "HEAD /doc_meta"),
        ("index", "HEAD /chunks"),
        ("index", "POST /chunks/_delete_by_query"),
        ("index", f"DELETE /doc_meta/_doc/{document.id}"),
        # 数据库记录最后删
        ("db", "delete:documents"),
        ("db", "commit:"),
    ]
    assert not path.exists()
    assert session.documents == {}


def test_cleanup_refuses_a_document_that_is_not_deleted(events, index, storage):
    document = stored_document(storage, text_pdf(1), PDF.mime_type, "a.pdf")
    path = file_path(storage, document)
    session = FakeSession(events, document)

    with pytest.raises(PipelineError, match="拒绝清理") as excinfo:
        cleanup(document, session, storage, index)

    assert excinfo.value.retryable is False
    assert events == []
    assert path.exists()
    assert document.id in session.documents


def test_cleanup_of_an_already_removed_record_does_nothing(events, index, storage):
    document = deleted_document(storage)

    cleanup(document, FakeSession(events), storage, index)

    assert events == []


def test_cleanup_can_be_repeated_after_the_file_is_already_gone(events, index, storage):
    document = deleted_document(storage)
    storage.delete(document.storage_key)
    session = FakeSession(events, document)

    cleanup(document, session, storage, index)

    assert session.documents == {}


def test_cleanup_keeps_file_and_record_when_the_index_cannot_be_cleaned(events, index, storage):
    document = deleted_document(storage)
    path = file_path(storage, document)
    session = FakeSession(events, document)
    index.down = True

    with pytest.raises(TextIndexUnavailable):
        cleanup(document, session, storage, index)

    # 记录还在，重试时才找得到要删的东西
    assert path.exists()
    assert document.id in session.documents
    assert events == []


# ---- 登记 ----


def test_handlers_are_registered_for_parse_and_cleanup_only():
    # ocr、embed 不在这里：通用 Worker 不会领取它们
    assert registry.HANDLERS == {TASK_PARSE: handle_parse, TASK_CLEANUP: handle_cleanup}


@pytest.mark.parametrize("handler", [handle_parse, handle_cleanup])
def test_handlers_can_be_sent_to_a_spawned_subprocess(handler):
    # 子进程按“模块名 + 函数名”重新导入处理函数，所以它必须能被 pickle
    assert pickle.loads(pickle.dumps(handler)) is handler
