"""T21：embed 任务（图片 → CLIP → image_embeddings → 向量索引）。不需要数据库和 OpenSearch。

数据库会话、CLIP 服务和检索服务都是假的；三个直接写 SQL 的函数（加锁、查向量、存向量）
换成记账的假函数，它们的真实 SQL 在 tests/integration/test_embed_db.py 里测。
"""

import io
import json
import pickle
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from shared.tasks import TASK_EMBED, Task
from shared.text_index import OpenSearchClient, TextIndexUnavailable

from app.db.models import Document, ImageAsset
from app.modules.clip import ClipModel, ClipRejected, ClipUnavailable, EncodedImage
from app.modules.storage import LocalStorage
from app.modules.vector_index import VECTOR_DIM
from app.worker.handlers import PipelineError, handle_embed, run_embed
from app.worker.handlers import embed as embed_module

MODEL = ClipModel(model_name="ViT-B-16", model_version="cn_clip-1.6.0-5997ef32c50d", dim=512)
IMAGE_BYTES = b"\x89PNG\r\n\x1a\n-fake-image"


def vector(position: int = 0) -> list[float]:
    values = [0.0] * VECTOR_DIM
    values[position] = 1.0
    return values


# ---- 假对象 ----


class FakeSession:
    def __init__(self, events: list, document: Document | None, asset: ImageAsset | None):
        self.events = events
        self.document = document
        self.asset = asset
        # 第 n 次读取文档之前要做的事（模拟“编码期间文档被删除”）
        self.before_document_get: dict[int, object] = {}
        self._document_gets = 0

    def get(self, model, key, populate_existing=False):
        if model is Document:
            self._document_gets += 1
            hook = self.before_document_get.get(self._document_gets)
            if hook:
                hook()
            return self.document if self.document and self.document.id == key else None
        assert model is ImageAsset
        return self.asset if self.asset and self.asset.image_id == key else None

    def commit(self) -> None:
        self.events.append(("db", "commit"))


class FakeStore:
    """代替 lock_content / find_embedding / save_embedding，像数据库表一样按键存向量。"""

    def __init__(self, events: list) -> None:
        self.events = events
        self.rows: dict[tuple[str, str, str], list[float]] = {}

    def install(self, monkeypatch) -> None:
        monkeypatch.setattr(embed_module, "lock_content", self.lock)
        monkeypatch.setattr(embed_module, "find_embedding", self.find)
        monkeypatch.setattr(embed_module, "save_embedding", self.save)

    def lock(self, session, sha256) -> None:
        self.events.append(("db", f"lock:{sha256[:8]}"))

    def find(self, session, sha256, model):
        self.events.append(("db", "find"))
        return self.rows.get((sha256, model.model_name, model.model_version))

    def save(self, session, sha256, model, values) -> None:
        self.events.append(("db", "save"))
        self.rows.setdefault((sha256, model.model_name, model.model_version), values)


class FakeClip:
    def __init__(self, events: list) -> None:
        self.events = events
        self.health_model = MODEL
        self.encode_model = MODEL
        self.encoded: list[bytes] = []
        self.fail_with: Exception | None = None
        self.result = vector(7)

    def model(self) -> ClipModel:
        self.events.append(("clip", "health"))
        return self.health_model

    def encode_image(self, data: bytes) -> EncodedImage:
        self.events.append(("clip", "encode"))
        if self.fail_with is not None:
            raise self.fail_with
        self.encoded.append(data)
        return EncodedImage(model=self.encode_model, vector=self.result)


class FakeIndex:
    def __init__(self, events: list) -> None:
        self.events = events
        self.requests: list[httpx.Request] = []
        self.down = False
        self.missing = False

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("refused", request=request)
        self.requests.append(request)
        self.events.append(("index", f"{request.method} {request.url.path}"))
        if request.method == "HEAD" and self.missing:
            return httpx.Response(404)
        return httpx.Response(200, json={})

    def client(self) -> OpenSearchClient:
        return OpenSearchClient(
            "http://search.test:9200",
            timeout_seconds=1.0,
            transport=httpx.MockTransport(self.handle),
        )

    def written(self) -> list[dict]:
        return [
            json.loads(r.content)
            for r in self.requests
            if r.method == "PUT" and "/_doc/" in r.url.path
        ]


# ---- fixture 与辅助函数 ----


@pytest.fixture
def events() -> list:
    return []


@pytest.fixture
def storage(tmp_path) -> LocalStorage:
    return LocalStorage(tmp_path / "storage")


@pytest.fixture
def store(events, monkeypatch) -> FakeStore:
    fake = FakeStore(events)
    fake.install(monkeypatch)
    return fake


@pytest.fixture
def clip(events) -> FakeClip:
    return FakeClip(events)


@pytest.fixture
def index(events) -> FakeIndex:
    return FakeIndex(events)


def image_document(storage: LocalStorage, data: bytes = IMAGE_BYTES) -> tuple[Document, ImageAsset]:
    document_id = uuid.uuid4()
    stored = storage.put(io.BytesIO(data), document_id=document_id)
    document = Document(
        id=document_id,
        owner_id=uuid.uuid4(),
        filename="照片.png",
        mime_type="image/png",
        size_bytes=len(data),
        sha256=stored.sha256,
        storage_key=stored.storage_key,
        status="succeeded",
    )
    asset = ImageAsset(
        image_id=str(document_id), document_id=document_id, sha256=stored.sha256, width=8, height=8
    )
    return document, asset


def embed_task(document: Document, payload: dict | None = None) -> Task:
    return Task(
        id=uuid.uuid4(),
        task_type=TASK_EMBED,
        document_id=document.id,
        payload={"image_id": str(document.id)} if payload is None else payload,
        attempts=1,
        max_attempts=3,
    )


def run(document, session, storage, index, clip, payload=None) -> None:
    run_embed(
        embed_task(document, payload),
        session=session,
        storage=storage,
        index=index.client(),
        clip=clip,
    )


# ---- 正常路径 ----


def test_new_image_is_encoded_stored_and_indexed(events, storage, store, clip, index):
    document, asset = image_document(storage)
    session = FakeSession(events, document, asset)

    run(document, session, storage, index, clip)

    assert clip.encoded == [IMAGE_BYTES]
    assert store.rows == {(asset.sha256, MODEL.model_name, MODEL.model_version): vector(7)}
    assert events == [
        ("clip", "health"),
        # 先加锁再查：同内容的两个任务排队，后到的看得到先到的结果
        ("db", f"lock:{asset.sha256[:8]}"),
        ("db", "find"),
        ("clip", "encode"),
        ("db", "save"),
        # 向量先进数据库再写索引：索引丢了能从数据库重建（D10）
        ("db", "commit"),
        ("index", "HEAD /image_vectors"),
        ("index", f"PUT /image_vectors/_doc/{document.id}"),
    ]
    (written,) = index.written()
    assert written == {
        "image_id": str(document.id),
        "document_id": str(document.id),
        "sha256": asset.sha256,
        "model_name": MODEL.model_name,
        "model_version": MODEL.model_version,
        "vector": vector(7),
    }


def test_duplicate_content_is_encoded_only_once(events, storage, store, clip, index):
    """🧪 重复图片只编码一次：内容相同的第二个文档直接复用数据库里的向量。"""
    first, first_asset = image_document(storage)
    second, second_asset = image_document(storage)
    assert first_asset.sha256 == second_asset.sha256

    run(first, FakeSession(events, first, first_asset), storage, index, clip)
    run(second, FakeSession(events, second, second_asset), storage, index, clip)

    assert clip.encoded == [IMAGE_BYTES]
    assert len(store.rows) == 1
    # 两个文档在索引里各有一条，向量相同
    assert [w["document_id"] for w in index.written()] == [str(first.id), str(second.id)]
    assert index.written()[0]["vector"] == index.written()[1]["vector"]


def test_running_twice_gives_the_same_result(events, storage, store, clip, index):
    document, asset = image_document(storage)

    run(document, FakeSession(events, document, asset), storage, index, clip)
    run(document, FakeSession(events, document, asset), storage, index, clip)

    assert clip.encoded == [IMAGE_BYTES]
    assert len(store.rows) == 1
    # 两次写的是同一个 _id：覆盖而不是追加
    paths = {r.url.path for r in index.requests if r.method == "PUT"}
    assert paths == {f"/image_vectors/_doc/{document.id}"}


def test_missing_vector_index_is_created(events, storage, store, clip, index):
    document, asset = image_document(storage)
    index.missing = True

    run(document, FakeSession(events, document, asset), storage, index, clip)

    assert ("index", "PUT /image_vectors") in events


def test_a_different_model_gets_its_own_vector(events, storage, store, clip, index):
    document, asset = image_document(storage)
    run(document, FakeSession(events, document, asset), storage, index, clip)

    other = ClipModel(model_name="ViT-B-16", model_version="cn_clip-1.7.0-aaaaaaaaaaaa", dim=512)
    clip.health_model = clip.encode_model = other
    run(document, FakeSession(events, document, asset), storage, index, clip)

    assert len(clip.encoded) == 2
    assert len(store.rows) == 2
    assert index.written()[-1]["model_version"] == other.model_version


# ---- 文档被删除 ----


def test_document_deleted_before_start_does_nothing(events, storage, store, clip, index):
    document, asset = image_document(storage)
    document.deleted_at = datetime.now(UTC)

    run(document, FakeSession(events, document, asset), storage, index, clip)

    assert events == []


def test_document_deleted_during_encoding_is_not_indexed(events, storage, store, clip, index):
    document, asset = image_document(storage)
    session = FakeSession(events, document, asset)
    session.before_document_get[2] = lambda: setattr(document, "deleted_at", datetime.now(UTC))

    run(document, session, storage, index, clip)

    # 向量照样存进数据库（对同内容的其他图片有用），但不写索引
    assert len(store.rows) == 1
    assert index.requests == []


def test_document_deleted_while_indexing_has_its_vector_withdrawn(
    events, storage, store, clip, index
):
    document, asset = image_document(storage)
    session = FakeSession(events, document, asset)
    session.before_document_get[3] = lambda: setattr(document, "deleted_at", datetime.now(UTC))

    run(document, session, storage, index, clip)

    assert events[-2:] == [
        ("index", f"PUT /image_vectors/_doc/{document.id}"),
        ("index", "POST /image_vectors/_delete_by_query"),
    ]


# ---- 失败 ----


@pytest.mark.parametrize("payload", [{}, {"image_id": ""}, {"image_id": 5}])
def test_task_without_image_id_fails_permanently(events, storage, store, clip, index, payload):
    document, asset = image_document(storage)
    with pytest.raises(PipelineError):
        run(document, FakeSession(events, document, asset), storage, index, clip, payload)
    assert clip.encoded == []


def test_missing_image_record_fails_permanently(events, storage, store, clip, index):
    document, _ = image_document(storage)
    with pytest.raises(PipelineError):
        run(document, FakeSession(events, document, None), storage, index, clip)


def test_image_record_of_another_document_is_refused(events, storage, store, clip, index):
    document, _ = image_document(storage)
    other, other_asset = image_document(storage)
    with pytest.raises(PipelineError):
        run(
            document,
            FakeSession(events, document, other_asset),
            storage,
            index,
            clip,
            {"image_id": other_asset.image_id},
        )


def test_missing_file_fails_permanently_without_leaking_paths(events, storage, store, clip, index):
    document, asset = image_document(storage)
    storage.delete(document.storage_key)
    with pytest.raises(PipelineError) as excinfo:
        run(document, FakeSession(events, document, asset), storage, index, clip)
    # 失败原因会展示给用户，不得包含服务器路径
    assert "/" not in excinfo.value.message
    assert store.rows == {}


def test_rejected_image_is_not_retryable_and_nothing_is_written(
    events, storage, store, clip, index
):
    document, asset = image_document(storage)
    clip.fail_with = ClipRejected("CLIP 服务拒绝了请求（HTTP 422，INVALID_IMAGE）")

    with pytest.raises(ClipRejected) as excinfo:
        run(document, FakeSession(events, document, asset), storage, index, clip)

    assert excinfo.value.retryable is False
    assert store.rows == {}
    assert index.requests == []
    assert ("db", "commit") not in events


def test_clip_down_is_retryable(events, storage, store, clip, index):
    document, asset = image_document(storage)
    clip.fail_with = ClipUnavailable("CLIP 服务连接失败（ConnectError）")
    with pytest.raises(ClipUnavailable) as excinfo:
        run(document, FakeSession(events, document, asset), storage, index, clip)
    assert excinfo.value.retryable is True


def test_model_swapped_between_health_and_encode_is_retryable(events, storage, store, clip, index):
    document, asset = image_document(storage)
    clip.encode_model = ClipModel(model_name="RN50", model_version="v2", dim=512)
    with pytest.raises(ClipUnavailable):
        run(document, FakeSession(events, document, asset), storage, index, clip)
    assert store.rows == {}


def test_model_with_a_different_dimension_is_refused(events, storage, store, clip, index):
    document, asset = image_document(storage)
    clip.health_model = ClipModel(model_name="ViT-L-14", model_version="v", dim=768)
    with pytest.raises(PipelineError) as excinfo:
        run(document, FakeSession(events, document, asset), storage, index, clip)
    assert "重建向量索引" in excinfo.value.message
    assert clip.encoded == []


def test_index_down_after_storing_is_retryable_and_reuses_the_vector(
    events, storage, store, clip, index
):
    document, asset = image_document(storage)
    index.down = True
    with pytest.raises(TextIndexUnavailable):
        run(document, FakeSession(events, document, asset), storage, index, clip)
    assert len(store.rows) == 1

    # 重试时不再调用 CLIP
    index.down = False
    run(document, FakeSession(events, document, asset), storage, index, clip)
    assert clip.encoded == [IMAGE_BYTES]
    assert len(index.written()) == 1


# ---- 入口 ----


def test_lock_key_is_a_stable_signed_64_bit_integer():
    key = embed_module._lock_key("ab" * 32)
    assert key == embed_module._lock_key("ab" * 32)
    assert key != embed_module._lock_key("cd" * 32)
    assert -(2**63) <= key < 2**63


def test_handler_can_be_sent_to_a_spawned_subprocess():
    # 子进程按“模块名 + 函数名”重新导入处理函数，所以它必须能被 pickle
    assert pickle.loads(pickle.dumps(handle_embed)) is handle_embed
