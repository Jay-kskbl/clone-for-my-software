"""T14：解析流水线在真实数据库上的行为。需要 TEST_DATABASE_URL，未设置时全部跳过。

分三部分：
1. 文档状态跟随 parse 任务（shared/tasks.py 里新加的 SQL、任务重试）。
2. parse / cleanup 处理函数对数据库的读写（检索服务用假的网络层代替）。
3. 🧪 端到端：上传 PDF → Worker 处理 → chunks 索引里有数据 → 删除 → 清理干净。
   这一部分另外需要 TEST_OPENSEARCH_URL（装了 analysis-smartcn 的 OpenSearch），否则跳过。
"""

import io
import os
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import psycopg
import pymupdf
import pytest
from fastapi.testclient import TestClient
from shared import tasks
from shared.tasks import TASK_CLEANUP, TASK_OCR, TASK_PARSE, Task
from sqlalchemy import func, select

from app.config import Settings
from app.db.models import Document, DocumentChunk, ImageAsset, ProcessingTask, User
from app.main import create_app
from app.modules.auth import create_user
from app.modules.documents.tags import replace_document_tags
from app.modules.documents.tasks import retry_task
from app.modules.storage import LocalStorage
from app.modules.text_index import CHUNKS, DOC_META, INDEX_NAMES, OpenSearchClient
from app.worker.handlers import PipelineError, run_cleanup, run_parse
from app.worker.loop import PgTaskQueue, WorkerOptions, run_worker
from app.worker.registry import HANDLERS

PASSWORD = "correct-horse-battery"
PAGE_TEXT = "智能文档管理系统的设计目标是让扫描件和图片中的文字也能被检索。"
LEASE = 60.0

SETTINGS = SimpleNamespace(
    pdf_ocr_min_chars=20,
    parse_zip_max_total_bytes=50 * 1024 * 1024,
    parse_zip_max_entries=1000,
    parse_image_max_pixels=10_000_000,
    chunk_max_chars=500,
    chunk_overlap_chars=50,
)


# ---- 造数据 ----


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


def scanned_pdf(pages: int = 2) -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 100))
        pixmap.clear_with(200)
        page.insert_image(pymupdf.Rect(50, 50, 450, 250), pixmap=pixmap)
    data = doc.tobytes()
    doc.close()
    return data


def png_image() -> bytes:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 320, 200))
    pixmap.clear_with(180)
    return pixmap.tobytes("png")


@pytest.fixture
def conn(migrated_engine, test_database_url):
    connection = psycopg.connect(test_database_url, autocommit=True)
    yield connection
    connection.close()


@pytest.fixture
def owner(session) -> User:
    user = User(username="owner", password_hash="x")
    session.add(user)
    session.commit()
    return user


@pytest.fixture
def storage(tmp_path) -> LocalStorage:
    return LocalStorage(tmp_path / "storage")


@pytest.fixture
def make_document(session, owner, storage):
    """把一份真实的文件存进存储，并建好它的 Document 记录。"""

    def _make(data: bytes, mime_type: str = "application/pdf", name: str = "a.pdf") -> Document:
        document_id = uuid.uuid4()
        stored = storage.put(io.BytesIO(data), document_id=document_id)
        document = Document(
            id=document_id,
            owner_id=owner.id,
            filename=name,
            mime_type=mime_type,
            size_bytes=len(data),
            sha256=stored.sha256,
            storage_key=stored.storage_key,
        )
        session.add(document)
        session.commit()
        return document

    return _make


def add_task(session, document: Document, task_type: str = TASK_PARSE, *, max_attempts: int = 3):
    task = ProcessingTask(task_type=task_type, document_id=document.id, max_attempts=max_attempts)
    session.add(task)
    session.commit()
    return task.id


def claim(conn, task_type: str = TASK_PARSE) -> Task:
    task = tasks.claim(conn, worker_id="worker-a", task_types=(task_type,), lease_seconds=LEASE)
    assert task is not None
    return task


def fail(conn, task: Task, *, retryable: bool = True) -> str | None:
    return tasks.fail(
        conn, task_id=task.id, worker_id="worker-a", error="出错了", retryable=retryable
    )


def document_status(conn, document: Document) -> str:
    return conn.execute("SELECT status FROM documents WHERE id = %s", [document.id]).fetchone()[0]


def set_document_status(conn, document: Document, status: str) -> None:
    conn.execute("UPDATE documents SET status = %s WHERE id = %s", [status, document.id])


def expire_lease(conn, task_id) -> None:
    conn.execute(
        "UPDATE processing_tasks SET lease_expires_at = now() - interval '1 second' WHERE id = %s",
        [task_id],
    )


# ---- 1. 文档状态跟随 parse 任务 ----


def test_non_retryable_parse_failure_marks_the_document_failed(conn, session, make_document):
    document = make_document(text_pdf(1))
    add_task(session, document)
    set_document_status(conn, document, "processing")

    assert fail(conn, claim(conn), retryable=False) == "failed"

    assert document_status(conn, document) == "failed"


def test_retryable_failure_with_attempts_left_does_not_mark_the_document_failed(
    conn, session, make_document
):
    document = make_document(text_pdf(1))
    add_task(session, document, max_attempts=3)
    set_document_status(conn, document, "processing")

    assert fail(conn, claim(conn)) == "pending"

    # 任务回到队列等待重试，文档仍显示“处理中”
    assert document_status(conn, document) == "processing"


def test_last_allowed_attempt_failing_marks_the_document_failed(conn, session, make_document):
    document = make_document(text_pdf(1))
    add_task(session, document, max_attempts=2)

    assert fail(conn, claim(conn)) == "pending"
    assert document_status(conn, document) == "pending"
    assert fail(conn, claim(conn)) == "failed"

    assert document_status(conn, document) == "failed"


def test_task_of_a_crashed_worker_running_out_of_attempts_marks_the_document_failed(
    conn, session, make_document
):
    # 处理函数没有机会报告任何东西：Worker 崩溃，租约过期，任务被回收
    document = make_document(text_pdf(1))
    task_id = add_task(session, document, max_attempts=1)
    claim(conn)
    set_document_status(conn, document, "processing")
    expire_lease(conn, task_id)

    assert tasks.reclaim_expired(conn) == 1

    assert document_status(conn, document) == "failed"


def test_reclaimed_task_with_attempts_left_leaves_the_document_alone(conn, session, make_document):
    document = make_document(text_pdf(1))
    task_id = add_task(session, document, max_attempts=3)
    claim(conn)
    set_document_status(conn, document, "processing")
    expire_lease(conn, task_id)

    assert tasks.reclaim_expired(conn) == 1

    assert document_status(conn, document) == "processing"


def test_failure_of_other_task_types_does_not_change_the_document(conn, session, make_document):
    # 文档状态只反映 parse 任务
    document = make_document(text_pdf(1))
    set_document_status(conn, document, "succeeded")
    for task_type in (TASK_OCR, TASK_CLEANUP):
        add_task(session, document, task_type)
        assert fail(conn, claim(conn, task_type), retryable=False) == "failed"

    assert document_status(conn, document) == "succeeded"


def test_a_failed_parse_task_does_not_overwrite_a_succeeded_document(conn, session, make_document):
    document = make_document(text_pdf(1))
    add_task(session, document)
    task = claim(conn)
    set_document_status(conn, document, "succeeded")

    assert fail(conn, task, retryable=False) == "failed"

    assert document_status(conn, document) == "succeeded"


def test_only_the_document_of_the_failed_task_is_touched(conn, session, make_document):
    mine, other = make_document(text_pdf(1)), make_document(text_pdf(1), name="b.pdf")
    add_task(session, mine)

    fail(conn, claim(conn), retryable=False)

    assert document_status(conn, mine) == "failed"
    assert document_status(conn, other) == "pending"


def test_retrying_a_failed_parse_task_puts_the_document_back_to_pending(
    conn, session, owner, make_document
):
    document = make_document(text_pdf(1))
    task_id = add_task(session, document)
    fail(conn, claim(conn), retryable=False)
    assert document_status(conn, document) == "failed"

    task = retry_task(session, owner, task_id)

    assert task.status == "pending"
    assert document_status(conn, document) == "pending"


def test_retrying_a_failed_ocr_task_does_not_change_the_document(
    conn, session, owner, make_document
):
    document = make_document(text_pdf(1))
    set_document_status(conn, document, "failed")
    task_id = add_task(session, document, TASK_OCR)
    fail(conn, claim(conn, TASK_OCR), retryable=False)

    retry_task(session, owner, task_id)

    assert document_status(conn, document) == "failed"


# ---- 2. 处理函数对数据库的读写（检索服务是假的）----


class FakeIndex:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, json={})

    def client(self) -> OpenSearchClient:
        return OpenSearchClient(
            "http://search.test:9200",
            timeout_seconds=1.0,
            transport=httpx.MockTransport(self.handle),
        )


@pytest.fixture
def index() -> FakeIndex:
    return FakeIndex()


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


def chunk_rows(session, document: Document) -> list[DocumentChunk]:
    session.expire_all()
    return list(
        session.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document.id)
            .order_by(DocumentChunk.seq)
        )
    )


def ocr_tasks(session, document: Document) -> list[ProcessingTask]:
    session.expire_all()
    return list(
        session.scalars(
            select(ProcessingTask).where(
                ProcessingTask.document_id == document.id, ProcessingTask.task_type == TASK_OCR
            )
        )
    )


def test_parse_writes_chunks_status_and_parse_version(conn, session, storage, index, make_document):
    document = make_document(text_pdf(2))

    parse(document, session, storage, index)

    rows = chunk_rows(session, document)
    assert [r.locator for r in rows] == [
        {"type": "pdf_page", "page": 1},
        {"type": "pdf_page", "page": 2},
    ]
    assert {r.source_type for r in rows} == {"body"}
    assert document_status(conn, document) == "succeeded"
    stored_version = conn.execute(
        "SELECT parse_version FROM documents WHERE id = %s", [document.id]
    ).fetchone()[0]
    assert stored_version == rows[0].parse_version


def test_parsing_twice_does_not_duplicate_chunks(session, storage, index, make_document):
    document = make_document(text_pdf(2))

    parse(document, session, storage, index)
    first = [(r.chunk_id, r.text) for r in chunk_rows(session, document)]
    parse(document, session, storage, index)

    assert [(r.chunk_id, r.text) for r in chunk_rows(session, document)] == first


def test_reparsing_with_new_parameters_replaces_the_old_version(
    session, storage, index, make_document
):
    document = make_document(text_pdf(2))
    parse(document, session, storage, index)
    old_version = chunk_rows(session, document)[0].parse_version

    run_parse(
        task_for(document),
        session=session,
        storage=storage,
        index=index.client(),
        settings=SimpleNamespace(**{**vars(SETTINGS), "chunk_max_chars": 300}),
    )

    versions = {r.parse_version for r in chunk_rows(session, document)}
    assert len(versions) == 1 and old_version not in versions


def test_ocr_chunks_of_the_current_version_survive_a_reparse(
    session, storage, index, make_document
):
    document = make_document(text_pdf(1))
    parse(document, session, storage, index)
    (body,) = chunk_rows(session, document)
    # OCR Worker（T17）之后写入的一条片段，与正文片段同一个版本
    session.add(
        DocumentChunk(
            chunk_id=f"{document.id}:{body.parse_version}:1",
            document_id=document.id,
            parse_version=body.parse_version,
            seq=1,
            source_type="ocr",
            text="图片里的文字",
            locator={"type": "pdf_page", "page": 1},
        )
    )
    session.commit()

    parse(document, session, storage, index)

    assert [r.source_type for r in chunk_rows(session, document)] == ["body", "ocr"]


def test_scanned_pdf_creates_ocr_tasks_once(conn, session, storage, index, make_document):
    document = make_document(scanned_pdf(2))

    parse(document, session, storage, index)
    parse(document, session, storage, index)

    created = ocr_tasks(session, document)
    assert sorted(t.payload["locator"]["page"] for t in created) == [1, 2]
    assert {t.status for t in created} == {"pending"}
    assert chunk_rows(session, document) == []
    assert document_status(conn, document) == "succeeded"


def test_image_asset_is_written_once(session, storage, index, make_document):
    document = make_document(png_image(), "image/png", "照片.png")

    parse(document, session, storage, index)
    parse(document, session, storage, index)

    session.expire_all()
    (asset,) = session.scalars(select(ImageAsset).where(ImageAsset.document_id == document.id))
    assert (asset.image_id, asset.width, asset.height) == (str(document.id), 320, 200)
    assert asset.sha256 == document.sha256
    assert len(ocr_tasks(session, document)) == 1


def test_tags_from_the_database_reach_doc_meta(session, storage, index, make_document):
    import json

    document = make_document(text_pdf(1), name="年度报告.pdf")
    replace_document_tags(session, document.id, ["财务", "合同"])
    session.commit()

    parse(document, session, storage, index)

    request = next(r for r in index.requests if r.method == "PUT")
    body = json.loads(request.content)
    assert body["filename"] == "年度报告.pdf"
    assert sorted(body["tags"]) == ["合同", "财务"]


def test_soft_deleted_document_is_not_parsed(conn, session, storage, index, make_document):
    document = make_document(text_pdf(1))
    document.deleted_at = datetime.now(UTC)
    session.commit()

    parse(document, session, storage, index)

    assert chunk_rows(session, document) == []
    assert index.requests == []
    assert document_status(conn, document) == "pending"


def test_cleanup_removes_record_dependents_and_file(conn, session, storage, index, make_document):
    document = make_document(scanned_pdf(1))
    keep = make_document(text_pdf(1), name="keep.pdf")
    parse(document, session, storage, index)
    parse(keep, session, storage, index)
    path = storage.local_path(document.storage_key)
    document.deleted_at = datetime.now(UTC)
    session.add(ProcessingTask(task_type=TASK_CLEANUP, document_id=document.id))
    session.commit()

    run_cleanup(
        task_for(document, TASK_CLEANUP), session=session, storage=storage, index=index.client()
    )

    def count(table: str) -> int:
        return conn.execute(
            f"SELECT count(*) FROM {table} WHERE document_id = %s", [document.id]
        ).fetchone()[0]

    assert (
        conn.execute("SELECT count(*) FROM documents WHERE id = %s", [document.id]).fetchone()[0]
        == 0
    )
    # 级联删除：片段、任务（包括 cleanup 任务自己和未执行的 ocr 任务）都没了
    assert count("document_chunks") == 0
    assert count("processing_tasks") == 0
    assert not path.exists()
    # 别的文档不受影响
    assert len(chunk_rows(session, keep)) == 1
    assert storage.local_path(keep.storage_key).exists()


def test_cleanup_twice_is_harmless(session, storage, index, make_document):
    document = make_document(text_pdf(1))
    document.deleted_at = datetime.now(UTC)
    session.commit()
    task = task_for(document, TASK_CLEANUP)

    run_cleanup(task, session=session, storage=storage, index=index.client())
    run_cleanup(task, session=session, storage=storage, index=index.client())

    assert session.scalar(select(func.count()).select_from(Document)) == 0


def test_cleanup_refuses_a_live_document(conn, session, storage, index, make_document):
    document = make_document(text_pdf(1))

    with pytest.raises(PipelineError):
        run_cleanup(
            task_for(document, TASK_CLEANUP),
            session=session,
            storage=storage,
            index=index.client(),
        )

    assert document_status(conn, document) == "pending"
    assert storage.local_path(document.storage_key).exists()


# ---- 3. 🧪 端到端：真实数据库 + 真实 OpenSearch + 真实 Worker 子进程 ----

OPENSEARCH_URL = os.environ.get("TEST_OPENSEARCH_URL")
needs_opensearch = pytest.mark.skipif(
    not OPENSEARCH_URL, reason="未设置 TEST_OPENSEARCH_URL，端到端测试未运行"
)
JWT_SECRET = "integration-test-secret-not-used-anywhere-else-0123456789"


@pytest.fixture
def e2e(migrated_engine, test_database_url, tmp_path, monkeypatch):
    """一套完整的环境：API、存储目录、带独立前缀的索引。

    任务处理函数在子进程里自己读配置，所以配置通过环境变量传给它
    （环境变量的优先级高于 .env 文件）。
    """
    prefix = f"test_{uuid.uuid4().hex[:10]}_"
    env = {
        "DATABASE_URL": test_database_url,
        "OPENSEARCH_URL": OPENSEARCH_URL,
        "CLIP_SERVICE_URL": "http://127.0.0.1:1",
        "JWT_SECRET": JWT_SECRET,
        "STORAGE_ROOT": str(tmp_path / "storage"),
        "OPENSEARCH_INDEX_PREFIX": prefix,
    }
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    settings = Settings(
        _env_file=None,
        database_url=test_database_url,
        opensearch_url=OPENSEARCH_URL,
        clip_service_url="http://127.0.0.1:1",
        jwt_secret=JWT_SECRET,
        storage_root=tmp_path / "storage",
        opensearch_index_prefix=prefix,
    )
    index = OpenSearchClient(OPENSEARCH_URL, timeout_seconds=30.0, index_prefix=prefix)
    try:
        with TestClient(create_app(settings)) as client:
            yield SimpleNamespace(
                client=client, index=index, settings=settings, database_url=test_database_url
            )
    finally:
        for name in INDEX_NAMES:
            index.request("DELETE", f"/{index.index_name(name)}", also_accept={404})
        index.close()


def run_one_task(env) -> int:
    """启动真实的 Worker 主循环，处理一个任务后退出。处理函数在真实的子进程里执行。"""
    queue = PgTaskQueue(env.database_url, worker_id="e2e-worker", lease_seconds=LEASE)
    options = WorkerOptions(
        max_tasks=1,
        poll_seconds=0.1,
        heartbeat_seconds=5.0,
        task_timeout_seconds=120.0,
        memory_limit_mb=None,
    )
    try:
        return run_worker(queue, HANDLERS, options)
    finally:
        queue.reset()


def index_count(env, name: str, document_id: str) -> int:
    response = env.index.request(
        "POST",
        f"/{env.index.index_name(name)}/_count",
        json={"query": {"term": {"document_id": document_id}}},
        also_accept={404},
    )
    return response.json().get("count", 0)


def login(client) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "alice", "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@needs_opensearch
def test_upload_parse_index_then_delete_and_cleanup(e2e, session):
    create_user(session, "alice", PASSWORD)
    headers = login(e2e.client)

    # 上传 PDF
    uploaded = e2e.client.post(
        "/api/documents",
        files={"file": ("设计说明.pdf", text_pdf(2), "application/octet-stream")},
        headers=headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["id"]
    assert uploaded.json()["status"] == "pending"
    stored = [p for p in e2e.settings.storage_root.rglob("*") if p.is_file()]
    assert len(stored) == 1

    # 等任务完成：Worker 领取 parse 任务，在子进程里执行
    assert run_one_task(e2e) == 1

    # chunks 索引中有该文档的数据
    assert index_count(e2e, CHUNKS, document_id) == 2
    assert index_count(e2e, DOC_META, document_id) == 1
    detail = e2e.client.get(f"/api/documents/{document_id}", headers=headers).json()
    assert detail["status"] == "succeeded"
    hits = e2e.index.request(
        "POST",
        f"/{e2e.index.index_name(CHUNKS)}/_search",
        json={"query": {"match": {"text": "扫描件"}}},
    ).json()["hits"]["hits"]
    assert {hit["_source"]["document_id"] for hit in hits} == {document_id}
    assert hits[0]["_source"]["locator"]["type"] == "pdf_page"

    # 删除：立即不可见；cleanup 任务跑完后索引、文件、记录都清掉
    assert e2e.client.delete(f"/api/documents/{document_id}", headers=headers).status_code in (
        200,
        204,
    )
    assert e2e.client.get(f"/api/documents/{document_id}", headers=headers).status_code == 404
    assert run_one_task(e2e) == 1

    assert index_count(e2e, CHUNKS, document_id) == 0
    assert index_count(e2e, DOC_META, document_id) == 0
    assert not stored[0].exists()
    session.expire_all()
    assert session.get(Document, uuid.UUID(document_id)) is None


@needs_opensearch
def test_corrupt_upload_ends_as_failed_document_with_reason(e2e, session):
    create_user(session, "alice", PASSWORD)
    headers = login(e2e.client)
    uploaded = e2e.client.post(
        "/api/documents",
        files={"file": ("坏文件.pdf", b"%PDF-1.7\nnot really a pdf", "application/octet-stream")},
        headers=headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["id"]

    assert run_one_task(e2e) == 1

    # 上传成功但解析失败是合法状态：文件保留，任务失败并带原因，文档显示失败
    detail = e2e.client.get(f"/api/documents/{document_id}", headers=headers).json()
    assert detail["status"] == "failed"
    task = session.scalars(
        select(ProcessingTask).where(ProcessingTask.document_id == uuid.UUID(document_id))
    ).one()
    assert task.status == "failed"
    assert task.attempts == 1  # 文件本身是坏的：不重试
    assert "ParseError" in task.error
    assert index_count(e2e, CHUNKS, document_id) == 0
    # 文件名仍然可以检索到
    assert index_count(e2e, DOC_META, document_id) == 1
    assert len([p for p in e2e.settings.storage_root.rglob("*") if p.is_file()]) == 1
