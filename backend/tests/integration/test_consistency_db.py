"""T18 🧪：一致性检查在真实数据库上：收集、检测、修复。需要 TEST_DATABASE_URL。

检索服务用假的网络层代替（记录请求，按预置的数据应答）。
"""

import io
import json
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from shared.text_index import OpenSearchClient
from sqlalchemy import func, select

from app.db.models import Document, DocumentChunk, OCRResult, ProcessingTask, User
from app.modules.consistency import analyze, apply, collect_db, collect_disk, plan
from app.modules.consistency.model import IndexChunk, IndexState, Snapshot
from app.modules.documents.tags import replace_document_tags
from app.modules.storage import LocalStorage

V1 = "c1-m500-o50-aaaaaaaaaaaa"
V2 = "c1-m300-o50-bbbbbbbbbbbb"
PAGE1 = {"type": "pdf_page", "page": 1}


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

    def calls(self) -> list[str]:
        return [f"{r.method} {r.url.path}" for r in self.requests]


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
    def _make(name: str = "a.pdf", *, parse_version: str | None = V1) -> Document:
        document_id = uuid.uuid4()
        stored = storage.put(io.BytesIO(b"%PDF-1.7\n" + name.encode()), document_id=document_id)
        document = Document(
            id=document_id,
            owner_id=owner.id,
            filename=name,
            mime_type="application/pdf",
            size_bytes=10,
            sha256=stored.sha256,
            storage_key=stored.storage_key,
            status="succeeded",
            parse_version=parse_version,
        )
        session.add(document)
        session.commit()
        return document

    return _make


def add_chunk(session, document, seq, *, version=V1, source_type="body", locator=None):
    chunk = DocumentChunk(
        chunk_id=f"{document.id}:{version}:{seq}",
        document_id=document.id,
        parse_version=version,
        seq=seq,
        source_type=source_type,
        text=f"片段{seq}",
        locator=locator or PAGE1,
    )
    session.add(chunk)
    session.commit()
    return chunk


def index_matching(session) -> IndexState:
    """一个与数据库完全一致的索引快照。"""
    state = IndexState()
    documents = list(session.scalars(select(Document).where(Document.deleted_at.is_(None))))
    for document in documents:
        if document.parse_version is None:
            continue
        state.meta[str(document.id)] = (document.filename, ())
    for chunk in session.scalars(select(DocumentChunk)):
        state.chunks[chunk.chunk_id] = IndexChunk(
            chunk.chunk_id, str(chunk.document_id), chunk.parse_version
        )
    return state


def snapshot(session, storage, index_state=None) -> Snapshot:
    return Snapshot(
        db=collect_db(session),
        disk=collect_disk(storage._root),
        index=index_state or index_matching(session),
    )


def test_consistent_database_has_no_issues(session, storage, make_document):
    document = make_document()
    add_chunk(session, document, 0)

    assert analyze(snapshot(session, storage), min_age_seconds=0) == []


def test_collect_db_reads_tags_cleanup_tasks_and_ocr_targets(session, make_document):
    document = make_document()
    replace_document_tags(session, document.id, ["乙", "甲"])
    session.add(
        ProcessingTask(
            task_type="ocr",
            document_id=document.id,
            payload={"parse_version": V1, "locator": PAGE1},
        )
    )
    session.add(
        ProcessingTask(
            task_type="ocr",
            document_id=document.id,
            payload={"parse_version": V2, "locator": {"type": "pdf_page", "page": 9}},
        )
    )
    session.commit()

    db = collect_db(session)

    record = db.documents[str(document.id)]
    assert record.tags == tuple(sorted(("乙", "甲")))
    assert record.cleanup_pending is False
    # 只收当前版本的 ocr 任务
    assert db.ocr_targets[str(document.id)] == {json.dumps(PAGE1, sort_keys=True)}


# ---- 🧪 三类不一致：制造出来，再检测出来 ----


def test_file_deleted_from_disk_is_detected(session, storage, make_document):
    document = make_document()
    storage.delete(document.storage_key)

    issues = analyze(snapshot(session, storage), min_age_seconds=0)

    assert [(i.kind, i.document_id) for i in issues] == [("missing_file", str(document.id))]


def test_record_deleted_behind_the_index_is_detected_and_repaired(session, storage, make_document):
    document = make_document()
    add_chunk(session, document, 0)
    stale = index_matching(session)
    # 数据库里把记录硬删掉，索引快照里还留着（D27 的竞态）
    session.delete(session.get(Document, document.id))
    session.commit()
    storage.delete(document.storage_key)

    issues = analyze(snapshot(session, storage, stale), min_age_seconds=0)
    assert [i.kind for i in issues] == ["index_orphan"]

    index = FakeIndex()
    report = apply(
        plan(issues, ["index"]),
        session=session,
        client=index.client(),
        storage=storage,
        storage_root=storage._root,
    )

    assert f"DELETE /doc_meta/_doc/{document.id}" in index.calls()
    assert report.done


def test_old_version_chunks_are_detected_and_repaired(session, storage, make_document):
    document = make_document()
    add_chunk(session, document, 0)
    add_chunk(session, document, 1_000_000_000, version=V2, source_type="ocr")

    issues = analyze(snapshot(session, storage), min_age_seconds=0)
    assert "db_stale_chunks" in [i.kind for i in issues]

    apply(
        plan(issues, ["db-chunks"]),
        session=session,
        client=None,
        storage=storage,
        storage_root=storage._root,
    )

    session.expire_all()
    remaining = session.scalars(select(DocumentChunk.parse_version)).all()
    assert remaining == [V1]


# ---- 其他修复 ----


def test_stale_ocr_results_are_removed(session, storage, make_document):
    document = make_document()
    session.add(
        ProcessingTask(
            task_type="ocr",
            document_id=document.id,
            payload={"parse_version": V1, "locator": PAGE1},
        )
    )
    session.add_all(
        [
            OCRResult(
                document_id=document.id, locator=PAGE1, lines=[], model_name="m", model_version="v"
            ),
            OCRResult(
                document_id=document.id,
                locator={"type": "pdf_page", "page": 2},
                lines=[],
                model_name="m",
                model_version="v",
            ),
        ]
    )
    session.commit()

    issues = analyze(snapshot(session, storage), min_age_seconds=0)
    apply(
        plan(issues, ["ocr-results"]),
        session=session,
        client=None,
        storage=storage,
        storage_root=storage._root,
    )

    session.expire_all()
    assert session.scalars(select(OCRResult.locator)).all() == [PAGE1]


def test_deleted_document_without_cleanup_gets_a_cleanup_task(session, storage, make_document):
    document = make_document()
    document.deleted_at = datetime.now(UTC)
    session.commit()

    issues = analyze(snapshot(session, storage), min_age_seconds=0)
    assert "deleted_without_cleanup" in [i.kind for i in issues]
    apply(
        plan(issues, ["cleanup-tasks"]),
        session=session,
        client=None,
        storage=storage,
        storage_root=storage._root,
    )

    session.expire_all()
    assert (
        session.scalar(
            select(func.count())
            .select_from(ProcessingTask)
            .where(ProcessingTask.document_id == document.id, ProcessingTask.task_type == "cleanup")
        )
        == 1
    )
    # 补建之后再检查：交给清理任务，不再报告
    assert "deleted_without_cleanup" not in [
        i.kind for i in analyze(snapshot(session, storage), min_age_seconds=0)
    ]


def test_orphan_file_is_deleted_but_a_referenced_file_never_is(session, storage, make_document):
    document = make_document()
    orphan = storage.put(io.BytesIO(b"%PDF-1.7\norphan"), document_id=uuid.uuid4())

    issues = analyze(snapshot(session, storage), min_age_seconds=0)
    assert [i.target for i in issues if i.kind == "orphan_file"] == [orphan.storage_key]

    # 伪造一条指向有记录的文件的“问题”：修复前的复查必须挡住它
    from app.modules.consistency.model import Issue

    forged = Issue(
        kind="orphan_file", detail="x", repair="orphan-files", target=document.storage_key
    )
    report = apply(
        [*plan(issues, ["orphan-files"]), forged],
        session=session,
        client=None,
        storage=storage,
        storage_root=storage._root,
    )

    assert not (storage._root / orphan.storage_key).exists()
    assert (storage._root / document.storage_key).exists()
    assert any("没有删除" in line for line in report.skipped)


def test_reindex_rebuilds_a_document_from_the_database(session, storage, make_document):
    document = make_document("年度报告.pdf")
    replace_document_tags(session, document.id, ["财务"])
    session.commit()
    add_chunk(session, document, 0)
    add_chunk(session, document, 1)
    add_chunk(session, document, 9, version=V2)  # 旧版本，不应写进索引
    index_state = index_matching(session)
    index_state.meta[str(document.id)] = ("年度报告.pdf", ())  # 标签没同步

    issues = analyze(snapshot(session, storage, index_state), min_age_seconds=0)
    index = FakeIndex()
    apply(
        plan(issues, ["index"]),
        session=session,
        client=index.client(),
        storage=storage,
        storage_root=storage._root,
    )

    bulk = next(r for r in index.requests if r.url.path == "/_bulk")
    written = [
        json.loads(line)["index"]["_id"] for line in bulk.content.decode().splitlines()[0::2]
    ]
    assert written == [f"{document.id}:{V1}:0", f"{document.id}:{V1}:1"]
    meta = next(r for r in index.requests if r.method == "PUT" and "/_doc/" in r.url.path)
    assert json.loads(meta.content)["tags"] == ["财务"]


def test_rebuild_indices_recreates_both_and_reindexes_live_documents(
    session, storage, make_document
):
    live = make_document("live.pdf")
    add_chunk(session, live, 0)
    gone = make_document("gone.pdf")
    gone.deleted_at = datetime.now(UTC)
    session.commit()
    index_state = index_matching(session)
    index_state.missing_indices = ["chunks"]

    issues = analyze(snapshot(session, storage, index_state), min_age_seconds=0)
    index = FakeIndex()
    report = apply(
        plan(issues, ["rebuild-indices"]),
        session=session,
        client=index.client(),
        storage=storage,
        storage_root=storage._root,
    )

    calls = index.calls()
    assert calls[:2] == ["DELETE /doc_meta", "DELETE /chunks"]
    assert f"PUT /doc_meta/_doc/{live.id}" in calls
    assert f"PUT /doc_meta/_doc/{gone.id}" not in calls
    assert "1 个文档" in report.done[0]


def test_index_repairs_are_skipped_when_the_search_service_is_down(session, storage, make_document):
    document = make_document()
    state = index_matching(session)
    del state.meta[str(document.id)]

    issues = analyze(snapshot(session, storage, state), min_age_seconds=0)
    report = apply(
        plan(issues, ["index"]),
        session=session,
        client=None,
        storage=storage,
        storage_root=storage._root,
    )

    assert report.skipped == ["检索服务不可用，没有修复索引"]


def test_chunks_of_a_document_being_parsed_are_never_deleted(session, storage, make_document):
    # parse 已写入新版本的片段，parse_version 还是旧的：repair 不能把新片段当旧的删掉
    document = make_document()
    add_chunk(session, document, 0)
    add_chunk(session, document, 0, version=V2)
    session.add(ProcessingTask(task_type="parse", document_id=document.id, status="processing"))
    session.commit()

    issues = analyze(snapshot(session, storage), min_age_seconds=0)
    assert "db_stale_chunks" not in [i.kind for i in issues]

    # 即使检查时还没有任务（任务刚创建），修复前的复查也要挡住
    from app.modules.consistency.model import Issue

    forged = Issue(
        kind="db_stale_chunks", detail="x", document_id=str(document.id), repair="db-chunks"
    )
    report = apply(
        [forged], session=session, client=None, storage=storage, storage_root=storage._root
    )

    session.expire_all()
    assert sorted(session.scalars(select(DocumentChunk.parse_version)).all()) == [V1, V2]
    assert any("正在解析" in line for line in report.skipped)
