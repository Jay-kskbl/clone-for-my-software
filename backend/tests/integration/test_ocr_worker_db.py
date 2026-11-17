"""T17：OCR Worker 对真实数据库的读写（services/ocr_worker/ocr_worker/store.py）。

需要 TEST_DATABASE_URL，未设置时全部跳过。放在 backend 的集成测试里，是为了复用这里
建好表结构的测试库（迁移在 backend 里）。OCR Worker 的代码不依赖 backend。
"""

import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import select

from app.db.models import Document, DocumentChunk, OCRResult, User

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "services" / "ocr_worker"))

from ocr_worker.pipeline import OCR_SEQ_BASE, OCR_SEQ_BLOCK  # noqa: E402
from ocr_worker.store import PgStore  # noqa: E402
from shared.contracts import Chunk, OCRLine, PdfPageLocator, Point  # noqa: E402
from shared.contracts import OCRResult as OCRResultContract  # noqa: E402

VERSION = "c1-m500-o50-aaaaaaaaaaaa"
BOX = (Point(x=0, y=0), Point(x=10, y=0), Point(x=10, y=5), Point(x=0, y=5))


@pytest.fixture
def document(session) -> Document:
    owner = User(username="owner", password_hash="x")
    session.add(owner)
    session.flush()
    document_id = uuid.uuid4()
    document = Document(
        id=document_id,
        owner_id=owner.id,
        filename="scan.pdf",
        mime_type="application/pdf",
        size_bytes=1,
        sha256="0" * 64,
        storage_key=f"2026/{document_id}/{'0' * 64}.pdf",
        status="succeeded",
        parse_version=VERSION,
    )
    session.add(document)
    session.commit()
    return document


@pytest.fixture
def store(test_database_url, migrated_engine):
    s = PgStore(test_database_url)
    yield s
    s.reset()


def ocr_result(document: Document, page: int, texts: list[str]) -> OCRResultContract:
    return OCRResultContract(
        document_id=document.id,
        locator=PdfPageLocator(page=page),
        lines=[OCRLine(text=t, bbox=BOX, confidence=0.9) for t in texts],
        model_name="PP-OCRv5_mobile_det+PP-OCRv5_mobile_rec",
        model_version="paddleocr-3.7.0/det-aaaaaaaa/rec-bbbbbbbb",
    )


def chunks_for(document: Document, page: int, texts: list[str]) -> list[Chunk]:
    start = OCR_SEQ_BASE + (page - 1) * OCR_SEQ_BLOCK
    return [
        Chunk.build(
            document_id=document.id,
            parse_version=VERSION,
            seq=start + i,
            source_type="ocr",
            text=t,
            locator=PdfPageLocator(page=page),
        )
        for i, t in enumerate(texts)
    ]


def page_range(page: int) -> tuple[int, int]:
    start = OCR_SEQ_BASE + (page - 1) * OCR_SEQ_BLOCK
    return start, start + OCR_SEQ_BLOCK


def save(store, document, page, texts):
    store.save(
        ocr_result(document, page, texts),
        chunks_for(document, page, texts),
        parse_version=VERSION,
        seq_range=page_range(page),
    )


def rows(session, model, document):
    session.expire_all()
    return list(session.scalars(select(model).where(model.document_id == document.id)))


def test_document_state_is_read(store, document, session):
    state = store.document(document.id)

    assert (state.parse_version, state.deleted, state.storage_key) == (
        VERSION,
        False,
        document.storage_key,
    )
    assert store.document(uuid.uuid4()) is None

    document.deleted_at = datetime.now(UTC)
    session.commit()
    assert store.document(document.id).deleted


def test_save_writes_result_and_chunks(store, document, session):
    save(store, document, 2, ["第一行", "第二行"])

    (result,) = rows(session, OCRResult, document)
    assert result.locator == {"type": "pdf_page", "page": 2}
    assert [line["text"] for line in result.lines] == ["第一行", "第二行"]
    assert result.lines[0]["bbox"][2] == {"x": 10.0, "y": 5.0}
    assert result.model_version == "paddleocr-3.7.0/det-aaaaaaaa/rec-bbbbbbbb"
    chunks = rows(session, DocumentChunk, document)
    assert [(c.seq, c.source_type, c.text) for c in chunks] == [
        (OCR_SEQ_BASE + OCR_SEQ_BLOCK, "ocr", "第一行"),
        (OCR_SEQ_BASE + OCR_SEQ_BLOCK + 1, "ocr", "第二行"),
    ]


def test_saving_the_same_page_twice_replaces_instead_of_adding(store, document, session):
    save(store, document, 1, ["旧一", "旧二", "旧三"])
    save(store, document, 1, ["新"])

    assert len(rows(session, OCRResult, document)) == 1
    assert [c.text for c in rows(session, DocumentChunk, document)] == ["新"]


def test_other_pages_and_body_chunks_are_untouched(store, document, session):
    session.add(
        DocumentChunk(
            chunk_id=f"{document.id}:{VERSION}:0",
            document_id=document.id,
            parse_version=VERSION,
            seq=0,
            source_type="body",
            text="正文",
            locator={"type": "pdf_page", "page": 1},
        )
    )
    session.commit()

    save(store, document, 1, ["第一页"])
    save(store, document, 2, ["第二页"])
    save(store, document, 1, ["第一页重识别"])

    texts = sorted(c.text for c in rows(session, DocumentChunk, document))
    assert texts == sorted(["第一页重识别", "第二页", "正文"])
    assert len(rows(session, OCRResult, document)) == 2


def test_empty_result_still_replaces_the_old_one(store, document, session):
    save(store, document, 1, ["旧"])
    save(store, document, 1, [])

    (result,) = rows(session, OCRResult, document)
    assert result.lines == []
    assert rows(session, DocumentChunk, document) == []


def test_failure_inside_the_transaction_leaves_the_old_data(store, document, session):
    save(store, document, 1, ["旧"])
    bad = chunks_for(document, 1, ["新"])
    # 片段的文档不存在：外键约束让插入失败，整个事务回滚
    other = uuid.uuid4()
    bad = [
        c.model_copy(update={"document_id": other, "chunk_id": f"{other}:{VERSION}:{c.seq}"})
        for c in bad
    ]

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        store.save(
            ocr_result(document, 1, ["新"]), bad, parse_version=VERSION, seq_range=page_range(1)
        )
    store.reset()

    assert [c.text for c in rows(session, DocumentChunk, document)] == ["旧"]
    assert [line["text"] for line in rows(session, OCRResult, document)[0].lines] == ["旧"]


def test_hard_deleting_the_document_removes_ocr_rows(store, document, session):
    save(store, document, 1, ["文字"])

    session.delete(session.get(Document, document.id))
    session.commit()

    assert rows(session, OCRResult, document) == []
    assert rows(session, DocumentChunk, document) == []


def test_save_refuses_when_the_document_was_reparsed(store, document, session):
    document.parse_version = "c1-m300-o50-bbbbbbbbbbbb"
    session.commit()

    written = store.save(
        ocr_result(document, 1, ["文字"]),
        chunks_for(document, 1, ["文字"]),
        parse_version=VERSION,
        seq_range=page_range(1),
    )

    assert written is False
    assert rows(session, OCRResult, document) == []
    assert rows(session, DocumentChunk, document) == []


def test_save_refuses_when_the_document_was_deleted(store, document, session):
    document.deleted_at = datetime.now(UTC)
    session.commit()

    assert (
        store.save(
            ocr_result(document, 1, ["文字"]),
            chunks_for(document, 1, ["文字"]),
            parse_version=VERSION,
            seq_range=page_range(1),
        )
        is False
    )
    assert rows(session, OCRResult, document) == []


def test_ping(store):
    store.ping()
