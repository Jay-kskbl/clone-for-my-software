"""T07 🧪：任务队列在真实 PostgreSQL 上的行为（需要 TEST_DATABASE_URL，见 conftest.py）。

DEVPLAN 要求的四项：
- 崩溃恢复：领取后杀掉 Worker → 租约过期 → 任务被重新领取
- 并发：两个 Worker 不会领到同一任务
- 幂等：同一任务执行两次，结果不重复
- 超过最大重试次数后标记为 failed 并保存原因
"""

import multiprocessing
import os
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from shared import tasks
from shared.ids import make_chunk_id
from shared.tasks import LEASE_EXPIRED_ERROR, Task

from app.db.models import Document, ProcessingTask, User
from app.worker.loop import PgTaskQueue, WorkerOptions, run_worker

LEASE = 60.0


@pytest.fixture
def connect(migrated_engine, test_database_url):
    """打开到测试库的 psycopg 连接；测试结束时全部关闭（否则清库会被未结束的事务挡住）。"""
    opened: list[psycopg.Connection] = []

    def _connect(*, autocommit: bool = True) -> psycopg.Connection:
        conn = psycopg.connect(test_database_url, autocommit=autocommit)
        opened.append(conn)
        return conn

    yield _connect
    for conn in opened:
        conn.close()


@pytest.fixture
def conn(connect) -> psycopg.Connection:
    return connect()


@pytest.fixture
def document(session) -> Document:
    owner = User(username="owner", password_hash="x")
    session.add(owner)
    session.flush()
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        owner_id=owner.id,
        filename="a.pdf",
        mime_type="application/pdf",
        size_bytes=1,
        sha256="0" * 64,
        storage_key=f"2026/{doc_id}/{'0' * 64}.pdf",
    )
    session.add(doc)
    session.commit()
    return doc


@pytest.fixture
def add_task(session, document):
    """插入一个 pending 任务。每个任务的 created_at 比上一个晚一秒，领取顺序因此是确定的。"""
    base = datetime.now(UTC) - timedelta(hours=1)
    count = 0

    def _add(task_type: str = "parse", *, max_attempts: int = 3, payload: dict | None = None):
        nonlocal count
        task = ProcessingTask(
            task_type=task_type,
            document_id=document.id,
            max_attempts=max_attempts,
            payload=payload or {},
            created_at=base + timedelta(seconds=count),
        )
        count += 1
        session.add(task)
        session.commit()
        return task.id

    return _add


def claim(conn, worker_id: str = "worker-a", task_types=("parse",), lease_seconds: float = LEASE):
    return tasks.claim(
        conn, worker_id=worker_id, task_types=task_types, lease_seconds=lease_seconds
    )


def row(conn, task_id) -> dict:
    cur = conn.execute(
        """
        SELECT status, attempts, claimed_by, error,
               lease_expires_at IS NOT NULL AS has_lease,
               lease_expires_at > now() AS lease_valid,
               extract(epoch FROM lease_expires_at - now()) AS lease_remaining,
               started_at IS NOT NULL AS started,
               finished_at IS NOT NULL AS finished
        FROM processing_tasks WHERE id = %s
        """,
        [task_id],
    )
    names = [d.name for d in cur.description]
    return dict(zip(names, cur.fetchone(), strict=True))


def expire_lease(conn, task_id) -> None:
    """把租约改成已过期，等价于“Worker 崩溃后过了一个租约时长”，测试不必真的等。"""
    conn.execute(
        "UPDATE processing_tasks SET lease_expires_at = now() - interval '1 second' WHERE id = %s",
        [task_id],
    )


# ---- 领取 ----


def test_claim_marks_task_processing_with_lease(conn, add_task, document):
    task_id = add_task(payload={"pages": [1, 2]})

    task = claim(conn)

    assert task == Task(
        id=task_id,
        task_type="parse",
        document_id=document.id,
        payload={"pages": [1, 2]},
        attempts=1,
        max_attempts=3,
    )
    state = row(conn, task_id)
    assert state["status"] == "processing"
    assert state["attempts"] == 1
    assert state["claimed_by"] == "worker-a"
    assert state["lease_valid"] is True
    assert 50 < state["lease_remaining"] <= 60
    assert state["started"] is True
    assert state["finished"] is False


def test_claim_returns_oldest_first_and_none_when_empty(conn, add_task):
    first, second = add_task(), add_task()

    assert claim(conn).id == first
    assert claim(conn).id == second
    assert claim(conn) is None


def test_claim_only_takes_requested_types(conn, add_task):
    ocr_id = add_task("ocr")
    parse_id = add_task("parse")

    assert claim(conn, task_types=("parse", "cleanup")).id == parse_id
    assert claim(conn, task_types=("parse", "cleanup")) is None
    assert claim(conn, task_types=()) is None
    assert row(conn, ocr_id)["status"] == "pending"


# ---- 🧪 并发：两个 Worker 不会领到同一任务 ----


def test_uncommitted_claim_is_skipped_not_waited_for(connect, conn, add_task):
    first, second = add_task(), add_task()
    conn_a = connect(autocommit=False)
    # 先开一个事务，让下面的领取停在“已加锁、未提交”的状态——这正是两个 Worker 撞车的瞬间
    conn_a.execute("SELECT 1")
    task_a = claim(conn_a, worker_id="worker-a")

    # worker-b 此刻领取：不等待、不拿到同一个任务，而是跳过被锁住的行拿到下一个
    task_b = claim(conn, worker_id="worker-b")
    # 再领一次：唯一剩下的任务被 worker-a 锁着，应立即返回 None 而不是阻塞
    task_c = claim(conn, worker_id="worker-c")

    assert task_a.id == first
    assert task_b.id == second
    assert task_c is None

    conn_a.commit()
    assert row(conn, first)["claimed_by"] == "worker-a"
    assert row(conn, second)["claimed_by"] == "worker-b"


def test_many_workers_never_claim_the_same_task(connect, conn, add_task):
    task_ids = {add_task() for _ in range(40)}
    claimed: list[tuple[str, uuid.UUID]] = []
    errors: list[BaseException] = []
    lock = threading.Lock()
    start = threading.Barrier(8)

    def worker(worker_id: str, worker_conn: psycopg.Connection) -> None:
        try:
            start.wait(timeout=30)
            while (task := claim(worker_conn, worker_id=worker_id)) is not None:
                with lock:
                    claimed.append((worker_id, task.id))
        except BaseException as exc:  # noqa: BLE001 —— 线程里的失败要带回主线程
            errors.append(exc)

    # 连接在主线程里建好再交给线程，每个线程独占一个连接
    threads = [threading.Thread(target=worker, args=(f"worker-{i}", connect())) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert errors == []
    claimed_ids = [task_id for _worker, task_id in claimed]
    assert len(claimed_ids) == 40
    assert set(claimed_ids) == task_ids  # 每个任务恰好被领取一次
    for task_id in task_ids:
        assert row(conn, task_id)["attempts"] == 1


# ---- 🧪 崩溃恢复 ----


def _claim_then_die(database_url: str) -> None:
    """子进程：领取一个任务后立刻“崩溃”——不回写、不关连接、不做任何清理。"""
    conn = psycopg.connect(database_url, autocommit=True)
    task = tasks.claim(conn, worker_id="crashing-worker", task_types=["parse"], lease_seconds=2.0)
    os._exit(9 if task is not None else 1)


def test_task_of_killed_worker_is_reclaimed_after_lease_expires(conn, add_task, test_database_url):
    task_id = add_task()
    process = multiprocessing.get_context("spawn").Process(
        target=_claim_then_die, args=(test_database_url,)
    )
    process.start()
    process.join(timeout=60)
    assert process.exitcode == 9  # 确实领到了任务，然后死了

    # 租约还没过期：任务仍算在崩溃的 Worker 名下，别人领不到
    state = row(conn, task_id)
    assert state["status"] == "processing"
    assert state["claimed_by"] == "crashing-worker"
    assert claim(conn, worker_id="worker-b") is None

    time.sleep(2.5)  # 等租约（2 秒）过期

    task = claim(conn, worker_id="worker-b")
    assert task is not None
    assert task.id == task_id
    assert task.attempts == 2  # 崩溃的那一次也算一次尝试
    state = row(conn, task_id)
    assert state["status"] == "processing"
    assert state["claimed_by"] == "worker-b"
    assert state["error"] == LEASE_EXPIRED_ERROR


def test_reclaim_expired_returns_task_to_pending(conn, add_task):
    task_id = add_task()
    claim(conn)
    assert tasks.reclaim_expired(conn) == 0  # 租约有效时不回收

    expire_lease(conn, task_id)

    assert tasks.reclaim_expired(conn) == 1
    state = row(conn, task_id)
    assert state["status"] == "pending"
    assert state["claimed_by"] is None
    assert state["has_lease"] is False
    assert state["error"] == LEASE_EXPIRED_ERROR
    assert state["finished"] is False


def test_renew_keeps_the_task_from_being_reclaimed(conn, add_task):
    task_id = add_task()
    claim(conn)
    expire_lease(conn, task_id)

    assert tasks.renew(conn, task_id=task_id, worker_id="worker-a", lease_seconds=600) is True

    assert row(conn, task_id)["lease_remaining"] > 500
    assert tasks.reclaim_expired(conn) == 0
    assert claim(conn, worker_id="worker-b") is None


def test_late_write_back_from_previous_owner_is_rejected(conn, add_task):
    task_id = add_task()
    claim(conn, worker_id="worker-a")
    expire_lease(conn, task_id)
    assert claim(conn, worker_id="worker-b").id == task_id

    # worker-a 其实没死，只是卡住了；现在它醒过来想回写
    assert tasks.renew(conn, task_id=task_id, worker_id="worker-a", lease_seconds=LEASE) is False
    assert tasks.complete(conn, task_id=task_id, worker_id="worker-a") is False
    assert tasks.fail(conn, task_id=task_id, worker_id="worker-a", error="boom") is None

    state = row(conn, task_id)
    assert state["status"] == "processing"
    assert state["claimed_by"] == "worker-b"

    assert tasks.complete(conn, task_id=task_id, worker_id="worker-b") is True
    assert row(conn, task_id)["status"] == "succeeded"


def test_write_back_after_reclaim_to_pending_is_rejected(conn, add_task):
    task_id = add_task()
    claim(conn, worker_id="worker-a")
    expire_lease(conn, task_id)
    tasks.reclaim_expired(conn)

    assert tasks.complete(conn, task_id=task_id, worker_id="worker-a") is False
    assert row(conn, task_id)["status"] == "pending"


# ---- 完成与失败 ----


def test_complete_marks_succeeded_and_clears_previous_error(conn, add_task):
    task_id = add_task()
    claim(conn)
    assert tasks.fail(conn, task_id=task_id, worker_id="worker-a", error="first try") == "pending"
    claim(conn)

    assert tasks.complete(conn, task_id=task_id, worker_id="worker-a") is True

    state = row(conn, task_id)
    assert state["status"] == "succeeded"
    assert state["attempts"] == 2
    assert state["error"] is None
    assert state["has_lease"] is False
    assert state["finished"] is True
    # 已成功的任务不会再被领取
    assert claim(conn) is None


# ---- 🧪 超过最大重试次数后标记为 failed 并保存原因 ----


def test_failing_task_is_retried_up_to_max_attempts_then_failed(conn, add_task):
    task_id = add_task(max_attempts=3)

    for attempt in (1, 2):
        task = claim(conn)
        assert task.attempts == attempt
        status = tasks.fail(
            conn, task_id=task_id, worker_id="worker-a", error=f"ValueError: 第 {attempt} 次失败"
        )
        assert status == "pending"
        state = row(conn, task_id)
        assert state["status"] == "pending"
        assert state["error"] == f"ValueError: 第 {attempt} 次失败"
        assert state["finished"] is False

    assert claim(conn).attempts == 3
    status = tasks.fail(
        conn, task_id=task_id, worker_id="worker-a", error="ValueError: 第 3 次失败"
    )

    assert status == "failed"
    state = row(conn, task_id)
    assert state["status"] == "failed"
    assert state["attempts"] == 3
    assert state["error"] == "ValueError: 第 3 次失败"
    assert state["finished"] is True
    assert state["has_lease"] is False
    # failed 是终态：不会再被领取
    assert claim(conn) is None


def test_crashing_task_is_failed_after_max_attempts_with_reason(conn, add_task):
    # 每次都让 Worker 崩溃的文件：不会被无限重试
    task_id = add_task(max_attempts=2)

    for _ in range(2):
        assert claim(conn).id == task_id
        expire_lease(conn, task_id)

    assert claim(conn) is None  # 这次领取顺带回收，发现次数已用完
    state = row(conn, task_id)
    assert state["status"] == "failed"
    assert state["attempts"] == 2
    assert state["error"] == LEASE_EXPIRED_ERROR
    assert state["finished"] is True


def test_non_retryable_failure_goes_straight_to_failed(conn, add_task):
    task_id = add_task(max_attempts=3)
    claim(conn)

    status = tasks.fail(
        conn, task_id=task_id, worker_id="worker-a", error="压缩包超过解压上限", retryable=False
    )

    assert status == "failed"
    assert row(conn, task_id)["attempts"] == 1
    assert claim(conn) is None


def test_very_long_error_is_truncated(conn, add_task):
    task_id = add_task()
    claim(conn)

    tasks.fail(conn, task_id=task_id, worker_id="worker-a", error="x" * 100_000)

    assert len(row(conn, task_id)["error"]) == 4000


# ---- 🧪 幂等：同一任务执行两次，结果不重复 ----

PARSE_VERSION = "test-v1"
CHUNK_TEXTS = ["第一段", "第二段", "第三段"]


def write_chunks(conn: psycopg.Connection, task: Task) -> None:
    """一个按 GLOBAL §3.3 写法实现的处理函数：用确定性的 chunk_id 覆盖写入，而不是追加。

    真正的解析处理函数在 T14 实现；这里验证的是“任务框架 + 确定性 ID”这个组合确实幂等。
    """
    with conn.transaction():
        for seq, text in enumerate(CHUNK_TEXTS):
            conn.execute(
                """
                INSERT INTO document_chunks
                    (chunk_id, document_id, parse_version, seq, source_type, text, locator)
                VALUES (%s, %s, %s, %s, 'body', %s, '{"type": "pdf_page", "page": 1}')
                ON CONFLICT (chunk_id) DO UPDATE SET text = EXCLUDED.text
                """,
                [
                    make_chunk_id(task.document_id, PARSE_VERSION, seq),
                    task.document_id,
                    PARSE_VERSION,
                    seq,
                    text,
                ],
            )


def test_task_executed_twice_does_not_duplicate_results(conn, add_task, document):
    task_id = add_task()

    # 第一次：处理函数已经写完数据，但 Worker 在回写任务状态之前崩溃
    first = claim(conn, worker_id="worker-a")
    write_chunks(conn, first)
    expire_lease(conn, task_id)

    # 第二次：任务被重新领取，处理函数从头再执行一遍
    second = claim(conn, worker_id="worker-b")
    assert second.id == task_id
    assert second.attempts == 2
    write_chunks(conn, second)
    assert tasks.complete(conn, task_id=task_id, worker_id="worker-b") is True

    rows = conn.execute(
        "SELECT seq, text FROM document_chunks WHERE document_id = %s ORDER BY seq",
        [document.id],
    ).fetchall()
    assert rows == list(enumerate(CHUNK_TEXTS))
    assert row(conn, task_id)["status"] == "succeeded"


# ---- 主循环 + 真实队列 + 真实子进程 ----


def handler_writes_marker(task: Task) -> None:
    with open(task.payload["marker"], "w") as f:
        f.write(str(task.document_id))


def handler_always_fails(_task: Task) -> None:
    raise ValueError("文件已损坏")


OPTIONS = WorkerOptions(
    max_tasks=1,
    poll_seconds=0.1,
    heartbeat_seconds=1.0,
    task_timeout_seconds=60.0,
    memory_limit_mb=None,
)


def test_worker_loop_end_to_end_success(conn, add_task, document, test_database_url, tmp_path):
    marker = tmp_path / "done"
    task_id = add_task(payload={"marker": str(marker)})
    queue = PgTaskQueue(test_database_url, worker_id="loop-worker", lease_seconds=LEASE)

    try:
        processed = run_worker(queue, {"parse": handler_writes_marker}, OPTIONS)
    finally:
        queue.reset()

    assert processed == 1
    assert marker.read_text() == str(document.id)
    state = row(conn, task_id)
    assert state["status"] == "succeeded"
    assert state["attempts"] == 1


def test_worker_loop_end_to_end_failure_until_max_attempts(conn, add_task, test_database_url):
    task_id = add_task(max_attempts=2)
    queue = PgTaskQueue(test_database_url, worker_id="loop-worker", lease_seconds=LEASE)
    options = WorkerOptions(**{**OPTIONS.__dict__, "max_tasks": 2})

    try:
        processed = run_worker(queue, {"parse": handler_always_fails}, options)
    finally:
        queue.reset()

    assert processed == 2
    state = row(conn, task_id)
    assert state["status"] == "failed"
    assert state["attempts"] == 2
    assert state["error"] == "ValueError: 文件已损坏"
