"""T21：embed 任务在真实数据库上的行为。需要 TEST_DATABASE_URL，未设置时全部跳过。

CLIP 服务和检索服务用假的网络层代替；数据库是真的，验证加锁、按内容去重、唯一约束的 SQL。

🧪 重复图片只编码一次：内容相同的两个文档，CLIP 只被调用一次，image_embeddings 只有一行。
"""

import io
import json
import threading
import time
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pymupdf
import pytest
from shared.tasks import TASK_EMBED, TASK_OCR, Task
from shared.text_index import OpenSearchClient
from sqlalchemy import func, select

from app.db.models import Document, ImageAsset, ImageEmbedding, ProcessingTask, User
from app.db.session import make_session_factory
from app.modules.clip import ClipClient, ClipRejected
from app.modules.storage import LocalStorage
from app.modules.vector_index import VECTOR_DIM
from app.worker.handlers import run_embed, run_parse

MODEL = {"model_name": "ViT-B-16", "model_version": "cn_clip-1.6.0-5997ef32c50d", "dim": VECTOR_DIM}
SETTINGS = SimpleNamespace(
    pdf_ocr_min_chars=20,
    parse_zip_max_total_bytes=50 * 1024 * 1024,
    parse_zip_max_entries=1000,
    parse_image_max_pixels=10_000_000,
    chunk_max_chars=500,
    chunk_overlap_chars=50,
)


def png_image(gray: int = 180) -> bytes:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 64, 48))
    pixmap.clear_with(gray)
    return pixmap.tobytes("png")


def unit_vector(position: int) -> list[float]:
    values = [0.0] * VECTOR_DIM
    values[position] = 1.0
    return values


class FakeClipServer:
    """假的 CLIP 服务：记下每次编码；可以让编码慢一点，用来制造两个任务同时编码的场面。"""

    def __init__(self) -> None:
        self.encoded: list[bytes] = []
        self.delay = 0.0
        self.reject = False
        self._lock = threading.Lock()

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "device": "cpu", **MODEL})
        assert request.url.path == "/encode/image"
        if self.reject:
            return httpx.Response(422, json={"error": {"code": "INVALID_IMAGE", "message": "坏"}})
        time.sleep(self.delay)
        with self._lock:
            self.encoded.append(request.content)
        return httpx.Response(200, json={**MODEL, "vector": unit_vector(len(request.content) % 7)})

    def client(self) -> ClipClient:
        return ClipClient(
            "http://clip.test:8001",
            timeout_seconds=10.0,
            transport=httpx.MockTransport(self.handle),
        )


class FakeIndex:
    def __init__(self) -> None:
        self.written: list[dict] = []
        self._lock = threading.Lock()

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "PUT" and "/_doc/" in request.url.path:
            with self._lock:
                self.written.append(json.loads(request.content))
        return httpx.Response(200, json={})

    def client(self) -> OpenSearchClient:
        return OpenSearchClient(
            "http://search.test:9200",
            timeout_seconds=1.0,
            transport=httpx.MockTransport(self.handle),
        )


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
def clip() -> FakeClipServer:
    return FakeClipServer()


@pytest.fixture
def index() -> FakeIndex:
    return FakeIndex()


@pytest.fixture
def make_image(session, owner, storage):
    """存一张图片并建好 Document 和 ImageAsset（相当于 parse 已经成功）。"""

    def _make(data: bytes) -> Document:
        document_id = uuid.uuid4()
        stored = storage.put(io.BytesIO(data), document_id=document_id)
        document = Document(
            id=document_id,
            owner_id=owner.id,
            filename="照片.png",
            mime_type="image/png",
            size_bytes=len(data),
            sha256=stored.sha256,
            storage_key=stored.storage_key,
            status="succeeded",
        )
        session.add(document)
        session.flush()
        session.add(
            ImageAsset(
                image_id=str(document_id),
                document_id=document_id,
                sha256=stored.sha256,
                width=64,
                height=48,
            )
        )
        session.commit()
        return document

    return _make


def task_for(document: Document) -> Task:
    return Task(
        id=uuid.uuid4(),
        task_type=TASK_EMBED,
        document_id=document.id,
        payload={"image_id": str(document.id)},
        attempts=1,
        max_attempts=3,
    )


def embed(session, storage, index, clip, document) -> None:
    run_embed(
        task_for(document),
        session=session,
        storage=storage,
        index=index.client(),
        clip=clip.client(),
    )


def embedding_count(session) -> int:
    session.expire_all()
    return session.scalar(select(func.count()).select_from(ImageEmbedding))


# ---- 🧪 重复图片只编码一次 ----


def test_duplicate_images_are_encoded_once(session, storage, index, clip, make_image):
    first = make_image(png_image())
    second = make_image(png_image())
    assert first.sha256 == second.sha256

    embed(session, storage, index, clip, first)
    embed(session, storage, index, clip, second)

    assert len(clip.encoded) == 1
    assert embedding_count(session) == 1
    row = session.scalars(select(ImageEmbedding)).one()
    assert (row.sha256, row.model_name, row.model_version, row.dim) == (
        first.sha256,
        MODEL["model_name"],
        MODEL["model_version"],
        VECTOR_DIM,
    )
    assert len(row.vector) == VECTOR_DIM
    assert [w["document_id"] for w in index.written] == [str(first.id), str(second.id)]
    assert index.written[0]["vector"] == index.written[1]["vector"] == list(row.vector)


def test_concurrent_tasks_for_the_same_content_encode_once(
    migrated_engine, session, storage, index, clip, make_image
):
    """两个任务同时处理内容相同的图片：咨询锁让后到的那个等待，然后直接复用向量。"""
    documents = [make_image(png_image()) for _ in range(2)]
    clip.delay = 0.5
    factory = make_session_factory(migrated_engine)
    errors: list[BaseException] = []

    def worker(document):
        try:
            with factory() as own_session:
                embed(own_session, storage, index, clip, document)
        except BaseException as exc:  # noqa: BLE001 —— 交给主线程断言
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(d,)) for d in documents]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert len(clip.encoded) == 1
    assert embedding_count(session) == 1
    assert sorted(w["document_id"] for w in index.written) == sorted(str(d.id) for d in documents)


def test_different_content_gets_separate_vectors(session, storage, index, clip, make_image):
    embed(session, storage, index, clip, make_image(png_image(10)))
    embed(session, storage, index, clip, make_image(png_image(200)))

    assert len(clip.encoded) == 2
    assert embedding_count(session) == 2


def test_rerunning_a_task_does_not_add_rows(session, storage, index, clip, make_image):
    document = make_image(png_image())
    embed(session, storage, index, clip, document)
    embed(session, storage, index, clip, document)

    assert len(clip.encoded) == 1
    assert embedding_count(session) == 1


def test_rejected_image_leaves_no_row_and_releases_the_lock(
    session, storage, index, clip, make_image
):
    document = make_image(png_image())
    clip.reject = True
    with pytest.raises(ClipRejected):
        embed(session, storage, index, clip, document)
    session.rollback()
    assert embedding_count(session) == 0

    # 锁随事务回滚释放：同一内容的下一个任务不会被卡住
    clip.reject = False
    embed(session, storage, index, clip, make_image(png_image()))
    assert embedding_count(session) == 1


def test_embeddings_survive_document_deletion(session, storage, index, clip, make_image):
    """向量按内容共用、不挂文档（D10）：删除文档时不删向量，由一致性检查清理。"""
    document = make_image(png_image())
    embed(session, storage, index, clip, document)
    session.delete(session.get(Document, document.id))
    session.commit()

    assert embedding_count(session) == 1
    assert session.scalar(select(func.count()).select_from(ImageAsset)) == 0


def test_deleted_document_is_skipped(session, storage, index, clip, make_image):
    document = make_image(png_image())
    document.deleted_at = datetime.now(UTC)
    session.commit()

    embed(session, storage, index, clip, document)

    assert clip.encoded == []
    assert index.written == []


# ---- parse 建 embed 任务 ----


def test_parsing_an_image_creates_one_embed_task(session, owner, storage):
    data = png_image()
    document_id = uuid.uuid4()
    stored = storage.put(io.BytesIO(data), document_id=document_id)
    document = Document(
        id=document_id,
        owner_id=owner.id,
        filename="照片.png",
        mime_type="image/png",
        size_bytes=len(data),
        sha256=stored.sha256,
        storage_key=stored.storage_key,
    )
    session.add(document)
    session.commit()
    parse_task = Task(
        id=uuid.uuid4(),
        task_type="parse",
        document_id=document_id,
        payload={},
        attempts=1,
        max_attempts=3,
    )

    for _ in range(2):  # 重新解析不会再建一个
        run_parse(
            parse_task,
            session=session,
            storage=storage,
            index=FakeIndex().client(),
            settings=SETTINGS,
        )

    session.expire_all()
    tasks = session.scalars(
        select(ProcessingTask).where(ProcessingTask.document_id == document_id)
    ).all()
    embed_tasks = [t for t in tasks if t.task_type == TASK_EMBED]
    assert [t.payload for t in embed_tasks] == [{"image_id": str(document_id)}]
    assert embed_tasks[0].status == "pending"
    assert any(t.task_type == TASK_OCR for t in tasks)
