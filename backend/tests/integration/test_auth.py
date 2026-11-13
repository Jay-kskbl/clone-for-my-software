"""T06 🧪：认证与权限（需要真实 PostgreSQL，见 conftest.py）。

DEVPLAN 要求的四项：
- 未登录 401（不需要数据库的部分在 tests/unit/test_auth_api.py）
- 访问他人文档 403
- 管理员可见全部
- 共享后可见、取消共享后不可见
"""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.config import load_settings
from app.core.errors import (
    ForbiddenError,
    InvalidCredentialsError,
    NotFoundError,
    UsernameTakenError,
)
from app.core.security import create_access_token
from app.db.models import Document, DocumentShare, User
from app.modules.auth import __main__ as auth_cli
from app.modules.auth import (
    accessible_document_ids,
    authenticate,
    can_access,
    create_user,
    get_accessible_document,
)

PASSWORD = "correct-horse-battery"


def make_document(session, owner: User, name: str = "a.pdf") -> Document:
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        owner_id=owner.id,
        filename=name,
        mime_type="application/pdf",
        size_bytes=1,
        sha256="0" * 64,
        storage_key=f"2026/{doc_id}/{'0' * 64}.pdf",
    )
    session.add(doc)
    session.commit()
    return doc


def share(session, doc: Document, user: User) -> None:
    session.add(DocumentShare(document_id=doc.id, user_id=user.id))
    session.commit()


def unshare(session, doc: Document, user: User) -> None:
    session.delete(session.get(DocumentShare, (doc.id, user.id)))
    session.commit()


def login(client, username: str, password: str = PASSWORD) -> dict[str, str]:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def alice(session) -> User:
    return create_user(session, "alice", PASSWORD)


@pytest.fixture
def bob(session) -> User:
    return create_user(session, "bob", PASSWORD)


@pytest.fixture
def admin(session) -> User:
    return create_user(session, "root", PASSWORD, role="admin")


# ---- 注册、登录、me ----


def test_register_login_me_flow(client, session):
    resp = client.post("/api/auth/register", json={"username": "barry", "password": PASSWORD})

    assert resp.status_code == 201
    user = resp.json()
    assert set(user) == {"id", "username", "role", "created_at"}
    assert user["username"] == "barry"
    assert user["role"] == "user"

    resp = client.post("/api/auth/login", json={"username": "barry", "password": PASSWORD})

    assert resp.status_code == 200
    token = resp.json()
    assert token["token_type"] == "bearer"
    assert token["expires_in"] == 3600

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token['access_token']}"})

    assert resp.status_code == 200
    assert resp.json() == user


def test_password_is_stored_hashed(client, session):
    client.post("/api/auth/register", json={"username": "barry", "password": PASSWORD})

    stored = session.scalar(select(User).where(User.username == "barry"))

    assert stored.password_hash != PASSWORD
    assert stored.password_hash.startswith("$argon2id$")


def test_register_duplicate_username_is_409(client):
    body = {"username": "barry", "password": PASSWORD}
    assert client.post("/api/auth/register", json=body).status_code == 201

    resp = client.post("/api/auth/register", json=body)

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "USERNAME_TAKEN"


def test_create_user_duplicate_raises_and_session_still_usable(session, alice):
    with pytest.raises(UsernameTakenError):
        create_user(session, "alice", PASSWORD)

    assert create_user(session, "alice2", PASSWORD).username == "alice2"


@pytest.mark.parametrize(
    ("username", "password"),
    [("alice", "wrong-password-1"), ("nobody", PASSWORD), ("ALICE", PASSWORD)],
    ids=["wrong-password", "unknown-user", "different-case"],
)
def test_login_failure_is_401_and_does_not_say_which_part_was_wrong(
    client, alice, username, password
):
    resp = client.post("/api/auth/login", json={"username": username, "password": password})

    assert resp.status_code == 401
    assert resp.json()["error"] == {"code": "INVALID_CREDENTIALS", "message": "用户名或密码错误"}


def test_authenticate_returns_user_or_raises(session, alice):
    assert authenticate(session, "alice", PASSWORD).id == alice.id
    with pytest.raises(InvalidCredentialsError):
        authenticate(session, "alice", "wrong-password-1")


def test_token_of_deleted_user_is_401(client, session, alice):
    headers = login(client, "alice")
    session.delete(alice)
    session.commit()

    resp = client.get("/api/auth/me", headers=headers)

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


def test_expired_token_is_401(client, app, alice):
    token = create_access_token(
        alice.id,
        secret=app.state.settings.jwt_secret.get_secret_value(),
        expires_in_seconds=60,
        now=datetime(2020, 1, 1, tzinfo=UTC),
    )

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


def test_register_cannot_create_admin(client, session):
    resp = client.post(
        "/api/auth/register",
        json={"username": "sneaky", "password": PASSWORD, "role": "admin"},
    )

    assert resp.status_code == 422
    assert session.scalar(select(User).where(User.username == "sneaky")) is None


# ---- 管理员命令行 ----


def test_create_admin_command(client, session, monkeypatch, test_database_url):
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("OPENSEARCH_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("CLIP_SERVICE_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("JWT_SECRET", "integration-test-secret-not-used-anywhere-else-0123456789")
    # 只读环境变量，不读开发者本机的 .env
    monkeypatch.setattr(auth_cli, "load_settings", lambda: load_settings(env_file=None))
    monkeypatch.setattr(auth_cli.getpass, "getpass", lambda _prompt: PASSWORD)

    assert auth_cli.main(["create-admin", "root"]) == 0

    stored = session.scalar(select(User).where(User.username == "root"))
    assert stored.role == "admin"
    resp = client.get("/api/auth/me", headers=login(client, "root"))
    assert resp.json()["role"] == "admin"

    # 重名时失败，不覆盖已有账号
    assert auth_cli.main(["create-admin", "root"]) == 1


def test_create_admin_rejects_mismatched_or_weak_password(monkeypatch, capsys):
    answers = iter(["first-password-1", "second-password-2"])
    monkeypatch.setattr(auth_cli.getpass, "getpass", lambda _prompt: next(answers))
    assert auth_cli.main(["create-admin", "root"]) == 1

    monkeypatch.setattr(auth_cli.getpass, "getpass", lambda _prompt: "short")
    assert auth_cli.main(["create-admin", "root"]) == 1
    assert "short" not in capsys.readouterr().err


# ---- 权限函数 ----


def test_owner_can_access_own_document_only(session, alice, bob):
    alice_doc = make_document(session, alice)
    bob_doc = make_document(session, bob)

    assert can_access(session, alice, alice_doc) is True
    assert can_access(session, alice, bob_doc) is False
    assert accessible_document_ids(session, alice) == {alice_doc.id}
    assert accessible_document_ids(session, bob) == {bob_doc.id}


def test_admin_sees_all_documents(session, alice, bob, admin):
    alice_doc = make_document(session, alice)
    bob_doc = make_document(session, bob)

    assert can_access(session, admin, alice_doc) is True
    assert can_access(session, admin, bob_doc) is True
    assert accessible_document_ids(session, admin) == {alice_doc.id, bob_doc.id}


def test_share_grants_access_and_unshare_revokes_it_immediately(session, alice, bob):
    doc = make_document(session, alice)
    assert can_access(session, bob, doc) is False
    assert accessible_document_ids(session, bob) == set()

    share(session, doc, bob)

    assert can_access(session, bob, doc) is True
    assert accessible_document_ids(session, bob) == {doc.id}

    unshare(session, doc, bob)

    assert can_access(session, bob, doc) is False
    assert accessible_document_ids(session, bob) == set()
    # owner 不受影响
    assert can_access(session, alice, doc) is True


def test_share_is_per_user(session, alice, bob):
    carol = create_user(session, "carol", PASSWORD)
    doc = make_document(session, alice)

    share(session, doc, bob)

    assert can_access(session, carol, doc) is False
    assert accessible_document_ids(session, carol) == set()


def test_soft_deleted_document_is_invisible_to_everyone(session, alice, bob, admin):
    doc = make_document(session, alice)
    share(session, doc, bob)

    doc.deleted_at = datetime.now(UTC)
    session.commit()

    for user in (alice, bob, admin):
        assert can_access(session, user, doc) is False
        assert accessible_document_ids(session, user) == set()
        with pytest.raises(NotFoundError):
            get_accessible_document(session, user, doc.id)


def test_get_accessible_document_distinguishes_403_and_404(session, alice, bob):
    doc = make_document(session, alice)

    assert get_accessible_document(session, alice, doc.id).id == doc.id
    with pytest.raises(ForbiddenError):
        get_accessible_document(session, bob, doc.id)
    with pytest.raises(NotFoundError):
        get_accessible_document(session, bob, uuid.uuid4())


# ---- 🧪 经 HTTP：访问他人文档 403、管理员可见全部、共享与取消共享 ----


@pytest.fixture
def doc_client(app, client):
    """文档接口在 T08 才实现。这里挂一个只在测试中存在的最小路由，

    用来验证“令牌 → 当前用户 → 权限判断 → HTTP 状态码”这条完整链路。
    """
    router = APIRouter()

    @router.get("/test/documents/{document_id}")
    def read_document(document_id: uuid.UUID, user: CurrentUser, session: SessionDep):
        return {"id": str(get_accessible_document(session, user, document_id).id)}

    app.include_router(router)
    return client


def test_document_access_over_http(doc_client, session, alice, bob, admin):
    doc = make_document(session, alice)
    url = f"/test/documents/{doc.id}"

    assert doc_client.get(url).status_code == 401
    assert doc_client.get(url, headers=login(doc_client, "alice")).status_code == 200
    assert doc_client.get(url, headers=login(doc_client, "root")).status_code == 200

    bob_headers = login(doc_client, "bob")
    resp = doc_client.get(url, headers=bob_headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"

    # 共享后可见；同一个令牌，不需要重新登录
    share(session, doc, bob)
    assert doc_client.get(url, headers=bob_headers).status_code == 200

    # 取消共享后立即不可见
    unshare(session, doc, bob)
    assert doc_client.get(url, headers=bob_headers).status_code == 403

    resp = doc_client.get(f"/test/documents/{uuid.uuid4()}", headers=bob_headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"
