"""T08 🧪：文档管理（需要真实 PostgreSQL，见 conftest.py）。

DEVPLAN 要求的三项：
- 上传中途失败不留半成品
- 删除后列表和下载都不可见
- 非法类型被拒绝
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.models import Document, DocumentShare, DocumentTag, ProcessingTask, Tag
from app.modules.auth import create_user

PASSWORD = "correct-horse-battery"
PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PDF_MIME = "application/pdf"


@pytest.fixture
def alice(session):
    return create_user(session, "alice", PASSWORD)


@pytest.fixture
def bob(session):
    return create_user(session, "bob", PASSWORD)


@pytest.fixture
def admin(session):
    return create_user(session, "root", PASSWORD, role="admin")


def login(client, username: str) -> dict[str, str]:
    resp = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def as_alice(client, alice):
    return login(client, "alice")


@pytest.fixture
def as_bob(client, bob):
    return login(client, "bob")


@pytest.fixture
def as_admin(client, admin):
    return login(client, "root")


def upload(client, headers, *, name="a.pdf", content=PDF_BYTES, tags=None):
    return client.post(
        "/api/documents",
        files={"file": (name, content, "application/octet-stream")},
        data={"tags": tags} if tags else None,
        headers=headers,
    )


def upload_ok(client, headers, **kwargs) -> dict:
    resp = upload(client, headers, **kwargs)
    assert resp.status_code == 201, resp.text
    return resp.json()


def stored_files(app):
    root = app.state.settings.storage_root
    return [p for p in root.rglob("*") if p.is_file()]


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def listed_ids(client, headers, **params) -> list[str]:
    resp = client.get("/api/documents", headers=headers, params=params)
    assert resp.status_code == 200, resp.text
    return [item["id"] for item in resp.json()["items"]]


# ---- 上传 ----


def test_upload_stores_file_record_and_parse_task(client, app, session, alice, as_alice):
    body = upload_ok(client, as_alice, name="年度报告.pdf", tags=["财务", "2026"])

    assert set(body) == {
        "id",
        "filename",
        "mime_type",
        "size_bytes",
        "status",
        "tags",
        "owner",
        "access",
        "created_at",
        "updated_at",
    }
    assert body["filename"] == "年度报告.pdf"
    assert body["mime_type"] == PDF_MIME
    assert body["size_bytes"] == len(PDF_BYTES)
    assert body["status"] == "pending"
    assert body["tags"] == ["2026", "财务"]
    assert body["owner"] == {"id": str(alice.id), "username": "alice"}
    assert body["access"] == "owner"

    document = session.get(Document, uuid.UUID(body["id"]))
    assert document.owner_id == alice.id
    # 文件落在服务端生成的路径上，路径里没有用户给的文件名
    path = app.state.settings.storage_root / document.storage_key
    assert path.read_bytes() == PDF_BYTES
    assert stored_files(app) == [path]
    assert "年度报告" not in document.storage_key

    tasks = session.scalars(select(ProcessingTask)).all()
    assert [(t.task_type, t.document_id, t.status, t.attempts) for t in tasks] == [
        ("parse", document.id, "pending", 0)
    ]


def test_mime_type_comes_from_content_not_from_extension_or_header(client, as_alice):
    body = upload_ok(client, as_alice, name="photo.pdf", content=PNG_BYTES)

    assert body["mime_type"] == "image/png"
    assert body["filename"] == "photo.pdf"


# ---- 🧪 非法类型被拒绝 ----


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("notes.pdf", b"plain text pretending to be a pdf"),
        ("setup.pdf", b"MZ\x90\x00" + b"\x00" * 64),
        ("old.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64),
        ("archive.docx", b"PK\x03\x04" + b"\x00" * 64),
    ],
    ids=["text-as-pdf", "exe-as-pdf", "legacy-doc", "broken-zip-as-docx"],
)
def test_unsupported_content_is_415_and_leaves_nothing(
    client, app, session, as_alice, name, content
):
    resp = upload(client, as_alice, name=name, content=content)

    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
    assert count(session, Document) == 0
    assert count(session, ProcessingTask) == 0
    assert stored_files(app) == []


def test_too_large_is_413_and_leaves_nothing(client, app, session, as_alice):
    # 测试配置的上限是 64 KB。100 KB 没有超过“上限 + 表单余量”，所以通过了
    # Content-Length 预检，由存储层在复制时拒绝——这里测的就是这第二道检查
    resp = upload(client, as_alice, content=b"%PDF-1.4\n" + b"x" * (100 * 1024))

    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert count(session, Document) == 0
    assert stored_files(app) == []


@pytest.mark.parametrize(
    ("name", "content", "tags"),
    [
        ("empty.pdf", b"", None),
        ("x" * 256 + ".pdf", PDF_BYTES, None),
        ("a.pdf", PDF_BYTES, ["x" * 65]),
        ("a.pdf", PDF_BYTES, [f"t{i}" for i in range(21)]),
    ],
    ids=["empty-file", "filename-too-long", "tag-too-long", "too-many-tags"],
)
def test_invalid_upload_is_422_and_leaves_nothing(
    client, app, session, as_alice, name, content, tags
):
    resp = upload(client, as_alice, name=name, content=content, tags=tags)

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert count(session, Document) == 0
    assert count(session, Tag) == 0
    assert stored_files(app) == []


def test_upload_without_file_field_is_422(client, as_alice):
    resp = client.post("/api/documents", data={"tags": ["a"]}, headers=as_alice)

    assert resp.status_code == 422


# ---- 🧪 上传中途失败不留半成品 ----


def test_failure_while_moving_file_leaves_no_record_and_no_file(app, session, alice, monkeypatch):
    def broken_commit(_staged):
        raise OSError("disk full")

    monkeypatch.setattr(app.state.storage, "commit", broken_commit)
    # raise_server_exceptions=False：让未预期的异常走到统一的 500 响应，而不是在测试里直接抛出
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = upload(client, login(client, "alice"), tags=["财务"])

    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "disk full" not in resp.text
    assert count(session, Document) == 0
    assert count(session, ProcessingTask) == 0
    assert count(session, DocumentTag) == 0
    assert count(session, Tag) == 0
    assert stored_files(app) == []


def test_failure_at_database_commit_removes_the_already_moved_file(
    app, session, alice, monkeypatch
):
    from sqlalchemy.orm import Session

    real_commit = Session.commit
    seen_document = []

    def commit_fails_for_upload(self):
        # 只让“上传”的那次提交失败（会话里有新建的 Document）；登录等其他提交照常
        if any(isinstance(obj, Document) for obj in self.identity_map.values()):
            seen_document.append(True)
            raise RuntimeError("database went away")
        return real_commit(self)

    monkeypatch.setattr(Session, "commit", commit_fails_for_upload)
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = upload(client, login(client, "alice"))
    monkeypatch.undo()

    assert seen_document == [True]
    assert resp.status_code == 500
    assert count(session, Document) == 0
    assert count(session, ProcessingTask) == 0
    assert stored_files(app) == []


# ---- 列表与详情 ----


def test_list_shows_only_accessible_documents_newest_first(client, as_alice, as_bob, as_admin):
    first = upload_ok(client, as_alice, name="1.pdf")["id"]
    second = upload_ok(client, as_alice, name="2.pdf")["id"]
    bobs = upload_ok(client, as_bob, name="b.pdf")["id"]

    assert listed_ids(client, as_alice) == [second, first]
    assert listed_ids(client, as_bob) == [bobs]
    assert listed_ids(client, as_admin) == [bobs, second, first]

    resp = client.get("/api/documents", headers=as_admin)
    assert {item["access"] for item in resp.json()["items"]} == {"admin"}
    assert resp.json()["total"] == 3


def test_list_pagination(client, as_alice):
    ids = [upload_ok(client, as_alice, name=f"{i}.pdf")["id"] for i in range(5)]
    newest_first = ids[::-1]

    resp = client.get("/api/documents", headers=as_alice, params={"page": 2, "page_size": 2})

    body = resp.json()
    assert [item["id"] for item in body["items"]] == newest_first[2:4]
    assert (body["total"], body["page"], body["page_size"]) == (5, 2, 2)
    assert listed_ids(client, as_alice, page=3, page_size=2) == newest_first[4:]
    assert listed_ids(client, as_alice, page=4, page_size=2) == []


@pytest.mark.parametrize(
    "params",
    [{"page": 0}, {"page_size": 0}, {"page_size": 101}, {"status": "done"}, {"scope": "all"}],
)
def test_list_rejects_invalid_parameters(client, as_alice, params):
    resp = client.get("/api/documents", headers=as_alice, params=params)

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_filters_by_scope_status_and_tag(client, session, alice, bob, as_alice, as_bob):
    mine = upload_ok(client, as_alice, name="mine.pdf", tags=["财务"])["id"]
    shared = upload_ok(client, as_bob, name="shared.pdf", tags=["财务", "合同"])["id"]
    session.add(DocumentShare(document_id=uuid.UUID(shared), user_id=alice.id))
    session.get(Document, uuid.UUID(mine)).status = "succeeded"
    session.commit()

    assert listed_ids(client, as_alice) == [shared, mine]
    assert listed_ids(client, as_alice, scope="mine") == [mine]
    assert listed_ids(client, as_alice, scope="shared") == [shared]
    assert listed_ids(client, as_alice, status="succeeded") == [mine]
    assert listed_ids(client, as_alice, status="failed") == []
    assert listed_ids(client, as_alice, tag="财务") == [shared, mine]
    assert listed_ids(client, as_alice, tag="合同") == [shared]
    assert listed_ids(client, as_alice, tag="不存在") == []

    resp = client.get(f"/api/documents/{shared}", headers=as_alice)
    assert resp.json()["access"] == "shared"
    assert resp.json()["owner"]["username"] == "bob"


def test_detail_distinguishes_403_and_404(client, as_alice, as_bob, as_admin):
    doc = upload_ok(client, as_alice)["id"]

    assert client.get(f"/api/documents/{doc}", headers=as_alice).status_code == 200
    assert client.get(f"/api/documents/{doc}", headers=as_admin).json()["access"] == "admin"
    resp = client.get(f"/api/documents/{doc}", headers=as_bob)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"
    resp = client.get(f"/api/documents/{uuid.uuid4()}", headers=as_bob)
    assert resp.status_code == 404
    assert client.get("/api/documents/not-a-uuid", headers=as_bob).status_code == 422


def test_response_never_exposes_internal_fields(client, as_alice):
    doc = upload_ok(client, as_alice)

    listing = client.get("/api/documents", headers=as_alice).text
    for secret in ("storage_key", "sha256", "password", "deleted_at"):
        assert secret not in doc
        assert secret not in listing


# ---- 下载 ----


def test_download_returns_original_bytes_with_headers(client, as_alice):
    doc = upload_ok(client, as_alice, name="年度报告.pdf")["id"]

    resp = client.get(f"/api/documents/{doc}/download", headers=as_alice)

    assert resp.status_code == 200
    assert resp.content == PDF_BYTES
    assert resp.headers["content-type"] == PDF_MIME
    assert resp.headers["content-length"] == str(len(PDF_BYTES))
    assert resp.headers["x-content-type-options"] == "nosniff"
    disposition = resp.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert "filename*=UTF-8''%E5%B9%B4%E5%BA%A6%E6%8A%A5%E5%91%8A.pdf" in disposition


def test_download_permissions(client, as_alice, as_bob):
    doc = upload_ok(client, as_alice)["id"]

    assert client.get(f"/api/documents/{doc}/download").status_code == 401
    assert client.get(f"/api/documents/{doc}/download", headers=as_bob).status_code == 403
    resp = client.get(f"/api/documents/{uuid.uuid4()}/download", headers=as_bob)
    assert resp.status_code == 404


def test_download_when_file_is_missing_on_disk_is_500_not_404(app, session, alice):
    with TestClient(app, raise_server_exceptions=False) as client:
        headers = login(client, "alice")
        doc = upload_ok(client, headers)["id"]
        for path in stored_files(app):
            path.unlink()

        resp = client.get(f"/api/documents/{doc}/download", headers=headers)

    # 记录还在、文件丢了，是数据不一致，不能让用户以为“文档不存在”
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "INTERNAL_ERROR"


# ---- 🧪 删除后列表和下载都不可见 ----


def test_deleted_document_disappears_everywhere_immediately(
    client, app, session, alice, bob, as_alice, as_bob, as_admin
):
    doc = upload_ok(client, as_alice, tags=["财务"])["id"]
    other = upload_ok(client, as_alice, name="keep.pdf")["id"]
    session.add(DocumentShare(document_id=uuid.UUID(doc), user_id=bob.id))
    session.commit()
    assert listed_ids(client, as_bob) == [doc]

    resp = client.delete(f"/api/documents/{doc}", headers=as_alice)

    assert resp.status_code == 204
    assert resp.content == b""
    # owner、被共享者、管理员：列表、详情、下载、任务、标签里都看不到了
    assert listed_ids(client, as_alice) == [other]
    assert listed_ids(client, as_bob) == []
    assert listed_ids(client, as_admin) == [other]
    for headers in (as_alice, as_bob, as_admin):
        assert client.get(f"/api/documents/{doc}", headers=headers).status_code == 404
        assert client.get(f"/api/documents/{doc}/download", headers=headers).status_code == 404
        assert client.get(f"/api/documents/{doc}/tasks", headers=headers).status_code == 404
    assert client.get("/api/tags", headers=as_alice).json() == {"items": []}
    # 再删一次：对用户来说它已经不存在
    assert client.delete(f"/api/documents/{doc}", headers=as_alice).status_code == 404


def test_delete_is_soft_and_creates_cleanup_task(client, app, session, as_alice):
    doc = uuid.UUID(upload_ok(client, as_alice)["id"])

    client.delete(f"/api/documents/{doc}", headers=as_alice)

    # 记录和文件都还在，等清理任务（T14）异步删除
    session.expire_all()
    document = session.get(Document, doc)
    assert document.deleted_at is not None
    assert (app.state.settings.storage_root / document.storage_key).exists()
    tasks = session.scalars(select(ProcessingTask).where(ProcessingTask.document_id == doc)).all()
    assert sorted((t.task_type, t.status) for t in tasks) == [
        ("cleanup", "pending"),
        ("parse", "pending"),
    ]


def test_only_owner_or_admin_can_delete(client, session, bob, as_alice, as_bob, as_admin):
    doc = upload_ok(client, as_alice)["id"]
    stranger = client.delete(f"/api/documents/{doc}", headers=as_bob)
    session.add(DocumentShare(document_id=uuid.UUID(doc), user_id=bob.id))
    session.commit()
    shared_user = client.delete(f"/api/documents/{doc}", headers=as_bob)

    assert stranger.status_code == 403
    assert shared_user.status_code == 403  # 被共享者只读
    assert client.get(f"/api/documents/{doc}", headers=as_alice).status_code == 200
    assert client.delete(f"/api/documents/{doc}", headers=as_admin).status_code == 204


# ---- 共享 ----


def test_share_lifecycle(client, alice, bob, as_alice, as_bob):
    doc = upload_ok(client, as_alice)["id"]
    url = f"/api/documents/{doc}/shares"

    created = client.post(url, json={"username": "bob"}, headers=as_alice)

    assert created.status_code == 201
    assert created.json()["user"] == {"id": str(bob.id), "username": "bob"}
    assert client.get(f"/api/documents/{doc}", headers=as_bob).status_code == 200
    assert client.get(f"/api/documents/{doc}/download", headers=as_bob).content == PDF_BYTES

    # 重复共享：200 和已有记录，不报错、不产生第二条
    again = client.post(url, json={"username": "bob"}, headers=as_alice)
    assert again.status_code == 200
    assert again.json() == created.json()
    assert client.get(url, headers=as_alice).json() == {"items": [created.json()]}

    removed = client.delete(f"{url}/{bob.id}", headers=as_alice)

    assert removed.status_code == 204
    # 取消后立即不可见，bob 用的还是同一个令牌
    assert client.get(f"/api/documents/{doc}", headers=as_bob).status_code == 403
    assert listed_ids(client, as_bob) == []
    assert client.get(url, headers=as_alice).json() == {"items": []}
    assert client.delete(f"{url}/{bob.id}", headers=as_alice).status_code == 404


def test_share_errors(client, alice, bob, as_alice, as_bob):
    doc = upload_ok(client, as_alice)["id"]
    url = f"/api/documents/{doc}/shares"

    assert client.post(url, json={"username": "nobody"}, headers=as_alice).status_code == 404
    to_self = client.post(url, json={"username": "alice"}, headers=as_alice)
    assert to_self.status_code == 422
    assert to_self.json()["error"]["code"] == "VALIDATION_ERROR"
    assert client.post(url, json={}, headers=as_alice).status_code == 422
    missing = f"/api/documents/{uuid.uuid4()}/shares"
    assert client.post(missing, json={"username": "bob"}, headers=as_alice).status_code == 404


def test_shared_user_cannot_manage_shares_or_tags(client, as_alice, as_bob):
    carol_doc = upload_ok(client, as_alice)["id"]
    url = f"/api/documents/{carol_doc}/shares"
    client.post(url, json={"username": "bob"}, headers=as_alice)

    assert client.get(url, headers=as_bob).status_code == 403
    assert client.post(url, json={"username": "bob"}, headers=as_bob).status_code == 403
    resp = client.put(f"/api/documents/{carol_doc}/tags", json={"tags": ["x"]}, headers=as_bob)
    assert resp.status_code == 403


# ---- 标签 ----


def test_put_tags_replaces_the_whole_set(client, session, as_alice):
    doc = upload_ok(client, as_alice, tags=["旧"])["id"]
    url = f"/api/documents/{doc}/tags"

    resp = client.put(url, json={"tags": [" 财务 ", "2026", "财务"]}, headers=as_alice)

    assert resp.status_code == 200
    assert resp.json()["tags"] == ["2026", "财务"]
    assert client.get(f"/api/documents/{doc}", headers=as_alice).json()["tags"] == ["2026", "财务"]
    assert count(session, DocumentTag) == 2

    cleared = client.put(url, json={"tags": []}, headers=as_alice)

    assert cleared.json()["tags"] == []
    assert count(session, DocumentTag) == 0
    assert client.put(url, json={"tags": [""]}, headers=as_alice).status_code == 422
    assert client.put(url, json={}, headers=as_alice).status_code == 422


def test_same_tag_on_two_documents_is_one_tag_row(client, session, as_alice, as_bob):
    upload_ok(client, as_alice, tags=["财务"])
    upload_ok(client, as_bob, tags=["财务"])

    assert count(session, Tag) == 1
    assert count(session, DocumentTag) == 2


def test_tag_list_only_contains_tags_of_accessible_documents(client, as_alice, as_bob, as_admin):
    upload_ok(client, as_alice, tags=["财务", "2026"])
    upload_ok(client, as_bob, tags=["机密", "2026"])

    assert client.get("/api/tags", headers=as_alice).json() == {"items": ["2026", "财务"]}
    assert client.get("/api/tags", headers=as_bob).json() == {"items": ["2026", "机密"]}
    # 汉字之间的先后取决于数据库的排序规则，这里只比较内容
    assert set(client.get("/api/tags", headers=as_admin).json()["items"]) == {
        "2026",
        "机密",
        "财务",
    }


# ---- 任务 ----


def only_task(session, document_id: str) -> ProcessingTask:
    return session.scalars(
        select(ProcessingTask).where(ProcessingTask.document_id == uuid.UUID(document_id))
    ).one()


def mark_failed(session, task: ProcessingTask) -> None:
    task.status = "failed"
    task.attempts = 3
    task.error = "解析超时"
    task.claimed_by = None
    session.commit()


def test_document_tasks_listing(client, session, bob, as_alice, as_bob):
    doc = upload_ok(client, as_alice)["id"]

    resp = client.get(f"/api/documents/{doc}/tasks", headers=as_alice)

    assert resp.status_code == 200
    (task,) = resp.json()["items"]
    assert set(task) == {
        "id",
        "document_id",
        "task_type",
        "status",
        "attempts",
        "max_attempts",
        "error",
        "created_at",
        "started_at",
        "finished_at",
    }
    assert (task["document_id"], task["task_type"], task["status"]) == (doc, "parse", "pending")
    assert client.get(f"/api/documents/{doc}/tasks", headers=as_bob).status_code == 403
    session.add(DocumentShare(document_id=uuid.UUID(doc), user_id=bob.id))
    session.commit()
    assert client.get(f"/api/documents/{doc}/tasks", headers=as_bob).status_code == 200


def test_retry_puts_failed_task_back_in_queue(client, session, as_alice):
    doc = upload_ok(client, as_alice)["id"]
    task = only_task(session, doc)
    url = f"/api/tasks/{task.id}/retry"

    not_failed = client.post(url, headers=as_alice)
    assert not_failed.status_code == 409
    assert not_failed.json()["error"]["code"] == "TASK_NOT_RETRYABLE"

    mark_failed(session, task)
    resp = client.post(url, headers=as_alice)

    assert resp.status_code == 200
    body = resp.json()
    assert (body["status"], body["attempts"], body["error"]) == ("pending", 0, None)
    assert body["finished_at"] is None
    session.expire_all()
    assert only_task(session, doc).status == "pending"
    # 已经回到队列，再点一次是 409
    assert client.post(url, headers=as_alice).status_code == 409


def test_retry_permissions(client, session, bob, as_alice, as_bob, as_admin):
    doc = upload_ok(client, as_alice)["id"]
    task = only_task(session, doc)
    mark_failed(session, task)
    url = f"/api/tasks/{task.id}/retry"

    assert client.post(url).status_code == 401
    assert client.post(url, headers=as_bob).status_code == 403
    session.add(DocumentShare(document_id=uuid.UUID(doc), user_id=bob.id))
    session.commit()
    assert client.post(url, headers=as_bob).status_code == 403  # 被共享者不能重试
    assert client.post(f"/api/tasks/{uuid.uuid4()}/retry", headers=as_alice).status_code == 404
    assert client.post(url, headers=as_admin).status_code == 200


def test_tasks_of_deleted_document_are_only_retryable_by_admin(client, session, as_alice, as_admin):
    doc = upload_ok(client, as_alice)["id"]
    client.delete(f"/api/documents/{doc}", headers=as_alice)
    cleanup = session.scalars(
        select(ProcessingTask).where(ProcessingTask.task_type == "cleanup")
    ).one()
    mark_failed(session, cleanup)
    url = f"/api/tasks/{cleanup.id}/retry"

    assert client.post(url, headers=as_alice).status_code == 404
    assert client.post(url, headers=as_admin).status_code == 200


def test_admin_task_listing(client, session, as_alice, as_admin):
    doc = upload_ok(client, as_alice)["id"]
    upload_ok(client, as_alice, name="b.pdf")
    client.delete(f"/api/documents/{doc}", headers=as_alice)
    mark_failed(
        session,
        session.scalars(select(ProcessingTask).where(ProcessingTask.task_type == "cleanup")).one(),
    )

    forbidden = client.get("/api/tasks", headers=as_alice)
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"

    everything = client.get("/api/tasks", headers=as_admin).json()
    assert everything["total"] == 3
    assert sorted(t["task_type"] for t in everything["items"]) == ["cleanup", "parse", "parse"]

    failed = client.get("/api/tasks", headers=as_admin, params={"status": "failed"}).json()
    assert [t["task_type"] for t in failed["items"]] == ["cleanup"]
    parse = client.get("/api/tasks", headers=as_admin, params={"task_type": "parse"}).json()
    assert parse["total"] == 2
    paged = client.get("/api/tasks", headers=as_admin, params={"page_size": 2, "page": 2}).json()
    assert (len(paged["items"]), paged["total"], paged["page"]) == (1, 3, 2)
