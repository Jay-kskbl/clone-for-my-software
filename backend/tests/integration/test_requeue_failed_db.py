"""T24ae：requeue-failed 在真实 PostgreSQL 上的行为（需要 TEST_DATABASE_URL，见 conftest.py）。"""

import uuid
from datetime import UTC, datetime

import psycopg
import pytest
from shared import tasks

from app.db.models import Document, ProcessingTask, User
from app.modules.documents.__main__ import cmd_requeue_failed

V1 = "c1-m500-o50-aaaaaaaaaaaa"
NOW = datetime.now(UTC)


@pytest.fixture
def owner(session) -> User:
    user = User(username="owner", password_hash="x")
    session.add(user)
    session.commit()
    return user


@pytest.fixture
def make(session, owner):
    """建一个文档和它的一个任务，返回任务 id。"""

    def _make(task_type="embed", *, status="failed", payload=None, deleted=False, version=V1):
        doc_id = uuid.uuid4()
        session.add(
            Document(
                id=doc_id,
                owner_id=owner.id,
                filename="a.png",
                mime_type="image/png",
                size_bytes=1,
                sha256="0" * 64,
                storage_key=f"2026/{doc_id}/{'0' * 64}.png",
                parse_version=version,
                deleted_at=NOW if deleted else None,
            )
        )
        session.flush()
        task = ProcessingTask(
            task_type=task_type,
            document_id=doc_id,
            status=status,
            attempts=3,
            error="ClipUnavailable: 连接失败",
            started_at=NOW,
            finished_at=NOW if status in ("failed", "succeeded") else None,
            payload=payload
            or ({"image_id": "x"} if task_type == "embed" else {"parse_version": V1}),
        )
        session.add(task)
        session.commit()
        return task.id

    return _make


def state(session, task_id) -> ProcessingTask:
    session.expire_all()
    return session.get(ProcessingTask, task_id)


def test_dry_run_changes_nothing(session, make, capsys):
    task_id = make()

    assert cmd_requeue_failed(session, "embed", yes=False) == 0

    assert "1 个失败的 embed 任务" in capsys.readouterr().out
    assert state(session, task_id).status == "failed"


def test_only_failed_tasks_of_the_type_are_requeued(session, make, test_database_url):
    wanted = make()
    others = [make("ocr"), make(status="succeeded"), make(status="processing"), make(deleted=True)]
    before = {task_id: state(session, task_id).status for task_id in others}

    assert cmd_requeue_failed(session, "embed", yes=True) == 0

    task = state(session, wanted)
    assert (task.status, task.attempts) == ("pending", 0)
    assert task.error is None and task.started_at is None and task.finished_at is None
    assert {task_id: state(session, task_id).status for task_id in others} == before

    # 马上能被领取，不受重试间隔限制（T24ad）
    with psycopg.connect(test_database_url, autocommit=True) as conn:
        claimed = tasks.claim(
            conn,
            worker_id="w",
            task_types=["embed"],
            lease_seconds=60,
            retry_delays=(30.0, 120.0),
        )
    assert claimed is not None and claimed.id == wanted and claimed.attempts == 1


def test_ocr_tasks_of_an_old_version_are_left_alone(session, make):
    current = make("ocr")
    old = make("ocr", payload={"parse_version": "c1-m300-o50-bbbbbbbbbbbb"})

    assert cmd_requeue_failed(session, "ocr", yes=True) == 0

    assert state(session, current).status == "pending"
    assert state(session, old).status == "failed"
