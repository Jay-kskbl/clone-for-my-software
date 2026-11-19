"""T16：GET /api/documents/{id}/text。需要 TEST_DATABASE_URL，未设置时全部跳过。"""

import uuid
from datetime import UTC, datetime

import pytest

from app.db.models import Document, DocumentChunk, DocumentShare, User
from app.modules.auth import create_user

PASSWORD = "correct-horse-battery"
V1 = "c1-m500-o50-aaaaaaaaaaaa"
V2 = "c1-m300-o50-bbbbbbbbbbbb"


def login(client, username: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def alice(session) -> User:
    return create_user(session, "alice", PASSWORD)


@pytest.fixture
def bob(session) -> User:
    return create_user(session, "bob", PASSWORD)


def add_document(session, owner: User, *, parse_version: str | None = V1) -> Document:
    document_id = uuid.uuid4()
    document = Document(
        id=document_id,
        owner_id=owner.id,
        filename="说明.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size_bytes=1,
        sha256="0" * 64,
        storage_key=f"2026/{document_id}/{'0' * 64}.docx",
        status="succeeded" if parse_version else "pending",
        parse_version=parse_version,
    )
    session.add(document)
    session.commit()
    return document


def add_chunks(
    session,
    document: Document,
    count: int,
    *,
    version: str = V1,
    start: int = 0,
    source_type: str = "body",
) -> list[str]:
    ids = []
    for seq in range(start, start + count):
        chunk_id = f"{document.id}:{version}:{seq}"
        session.add(
            DocumentChunk(
                chunk_id=chunk_id,
                document_id=document.id,
                parse_version=version,
                seq=seq,
                source_type=source_type,
                text=f"第{seq}段",
                locator={"type": "docx_para", "para_index": seq},
            )
        )
        ids.append(chunk_id)
    session.commit()
    return ids


def url(document: Document) -> str:
    return f"/api/documents/{document.id}/text"


def test_returns_chunks_of_the_current_version_in_order(client, session, alice):
    document = add_document(session, alice)
    add_chunks(session, document, 3)
    add_chunks(session, document, 2, version=V2)  # 旧版本或新版本的残留，不该出现

    response = client.get(url(document), headers=login(client, "alice"))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert [item["seq"] for item in body["items"]] == [0, 1, 2]
    assert body["items"][0] == {
        "chunk_id": f"{document.id}:{V1}:0",
        "seq": 0,
        "source_type": "body",
        "text": "第0段",
        "locator": {"type": "docx_para", "para_index": 0},
    }


def test_pagination(client, session, alice):
    document = add_document(session, alice)
    add_chunks(session, document, 5)

    body = client.get(
        url(document), params={"page": 2, "page_size": 2}, headers=login(client, "alice")
    ).json()

    assert (body["total"], body["page"], body["page_size"]) == (5, 2, 2)
    assert [item["seq"] for item in body["items"]] == [2, 3]


def test_filter_by_source_type(client, session, alice):
    document = add_document(session, alice)
    add_chunks(session, document, 2)
    add_chunks(session, document, 1, start=2, source_type="ocr")

    body = client.get(
        url(document), params={"source_type": "ocr"}, headers=login(client, "alice")
    ).json()

    assert [item["seq"] for item in body["items"]] == [2]


def test_chunk_id_jumps_to_the_page_containing_it(client, session, alice):
    document = add_document(session, alice)
    ids = add_chunks(session, document, 7)

    body = client.get(
        url(document),
        params={"chunk_id": ids[5], "page_size": 2, "page": 1},
        headers=login(client, "alice"),
    ).json()

    # seq 5 前面有 5 个片段，每页 2 个 → 第 3 页（seq 4、5）
    assert body["page"] == 3
    assert ids[5] in [item["chunk_id"] for item in body["items"]]


def test_stale_chunk_id_falls_back_to_the_first_page(client, session, alice):
    document = add_document(session, alice, parse_version=V2)
    add_chunks(session, document, 3, version=V2)

    body = client.get(
        url(document),
        params={"chunk_id": f"{document.id}:{V1}:2"},
        headers=login(client, "alice"),
    ).json()

    assert body["page"] == 1
    assert len(body["items"]) == 3


@pytest.mark.parametrize("bad", ["not-a-chunk-id", f"{uuid.uuid4()}:{V1}:0"])
def test_invalid_or_foreign_chunk_id_is_422(client, session, alice, bad):
    document = add_document(session, alice)

    response = client.get(url(document), params={"chunk_id": bad}, headers=login(client, "alice"))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unparsed_document_returns_an_empty_list(client, session, alice):
    document = add_document(session, alice, parse_version=None)

    body = client.get(url(document), headers=login(client, "alice")).json()

    assert body == {"items": [], "total": 0, "page": 1, "page_size": 20}


def test_permissions(client, session, alice, bob):
    document = add_document(session, alice)
    add_chunks(session, document, 1)
    as_bob = login(client, "bob")

    assert client.get(url(document)).status_code == 401
    assert client.get(url(document), headers=as_bob).status_code == 403
    session.add(DocumentShare(document_id=document.id, user_id=bob.id))
    session.commit()
    assert client.get(url(document), headers=as_bob).status_code == 200


def test_deleted_or_unknown_document_is_404(client, session, alice):
    document = add_document(session, alice)
    document.deleted_at = datetime.now(UTC)
    session.commit()
    headers = login(client, "alice")

    assert client.get(url(document), headers=headers).status_code == 404
    assert client.get(f"/api/documents/{uuid.uuid4()}/text", headers=headers).status_code == 404


def test_invalid_source_type_is_422(client, session, alice):
    document = add_document(session, alice)

    response = client.get(
        url(document), params={"source_type": "pdf"}, headers=login(client, "alice")
    )

    assert response.status_code == 422


# ---- T24e：按页码穿插 OCR 片段（D44）----

OCR_BASE = 1_000_000_000  # 与 OCR Worker 的 OCR_SEQ_BASE 相同（D30）
OCR_BLOCK = 1000


def add_pdf_chunk(session, document: Document, seq: int, page: int, source_type: str) -> str:
    chunk_id = f"{document.id}:{V1}:{seq}"
    session.add(
        DocumentChunk(
            chunk_id=chunk_id,
            document_id=document.id,
            parse_version=V1,
            seq=seq,
            source_type=source_type,
            text=f"{source_type}-p{page}-{seq}",
            locator={"type": "pdf_page", "page": page},
        )
    )
    return chunk_id


def mixed_pdf(session, owner: User) -> tuple[Document, dict[str, str]]:
    """第 1、3 页有文字层，第 2、4 页是扫描件；第 3 页另有一段 OCR（页内的图片）。"""
    document = add_document(session, owner)
    document.filename = "混合.pdf"
    document.mime_type = "application/pdf"
    ids = {
        "body-p1a": add_pdf_chunk(session, document, 0, 1, "body"),
        "body-p1b": add_pdf_chunk(session, document, 1, 1, "body"),
        "body-p3": add_pdf_chunk(session, document, 2, 3, "body"),
        "ocr-p2": add_pdf_chunk(session, document, OCR_BASE + 1 * OCR_BLOCK, 2, "ocr"),
        "ocr-p3": add_pdf_chunk(session, document, OCR_BASE + 2 * OCR_BLOCK, 3, "ocr"),
        "ocr-p4a": add_pdf_chunk(session, document, OCR_BASE + 3 * OCR_BLOCK, 4, "ocr"),
        "ocr-p4b": add_pdf_chunk(session, document, OCR_BASE + 3 * OCR_BLOCK + 1, 4, "ocr"),
    }
    session.commit()
    return document, ids


PREVIEW_ORDER = ["body-p1a", "body-p1b", "ocr-p2", "body-p3", "ocr-p3", "ocr-p4a", "ocr-p4b"]


def test_ocr_chunks_are_interleaved_by_page_body_first(client, session, alice):
    document, ids = mixed_pdf(session, alice)

    body = client.get(
        url(document), params={"page_size": 100}, headers=login(client, "alice")
    ).json()

    assert [item["chunk_id"] for item in body["items"]] == [ids[k] for k in PREVIEW_ORDER]


def test_pages_follow_the_interleaved_order(client, session, alice):
    document, ids = mixed_pdf(session, alice)
    headers = login(client, "alice")

    seen = []
    for page in (1, 2, 3, 4):
        body = client.get(
            url(document), params={"page": page, "page_size": 2}, headers=headers
        ).json()
        seen += [item["chunk_id"] for item in body["items"]]

    assert seen == [ids[k] for k in PREVIEW_ORDER]


@pytest.mark.parametrize("key", PREVIEW_ORDER)
def test_chunk_id_jump_uses_the_same_order(client, session, alice, key):
    document, ids = mixed_pdf(session, alice)

    body = client.get(
        url(document),
        params={"chunk_id": ids[key], "page_size": 2},
        headers=login(client, "alice"),
    ).json()

    position = PREVIEW_ORDER.index(key)
    assert body["page"] == position // 2 + 1
    assert ids[key] in [item["chunk_id"] for item in body["items"]]


def test_source_type_filter_keeps_page_order(client, session, alice):
    document, ids = mixed_pdf(session, alice)

    body = client.get(
        url(document), params={"source_type": "ocr"}, headers=login(client, "alice")
    ).json()

    assert [item["chunk_id"] for item in body["items"]] == [
        ids[k] for k in ("ocr-p2", "ocr-p3", "ocr-p4a", "ocr-p4b")
    ]
