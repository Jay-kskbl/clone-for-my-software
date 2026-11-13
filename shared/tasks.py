"""M4 任务队列：直接在 PostgreSQL 的 processing_tasks 表上领取、续租、回写（附录 A2、A3）。

三个环境（main / ocr / clip）的 Worker 共用本模块，所以只依赖 psycopg，用原生 SQL，
不依赖 backend 里的 SQLAlchemy 模型。表结构见 docs/data-model.md。

状态流转：

    pending ──claim──▶ processing ──complete──▶ succeeded
       ▲                   │
       │                   ├─ fail / 租约过期，且 attempts < max_attempts ──▶ pending（等待重试）
       └───────────────────┘
                           └─ fail / 租约过期，且 attempts ≥ max_attempts ──▶ failed

三条约定：
1. attempts 在“领取”时加一，而不是在失败时。Worker 崩溃来不及回写也算一次尝试，
   所以一个必然让 Worker 崩溃的文件最多被尝试 max_attempts 次，不会无限重试。
2. renew / complete / fail 都要求“任务仍由我领取且状态为 processing”。Worker 卡住、
   租约被回收、任务被别人领走之后，它迟到的回写会被拒绝，不会覆盖别人的结果。
3. 时间一律用数据库的 now()，不用各个 Worker 进程自己的时钟。

每个函数自己开一个事务（连接已在事务中时是一个保存点），调用方不需要另外提交，
前提是连接处于 autocommit 模式，或调用方自己负责提交外层事务。
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import psycopg

# 任务类型。处理函数在各自的任务里实现：parse、cleanup 在 T14，ocr 在 T17，embed 在 T21。
TASK_PARSE = "parse"
TASK_OCR = "ocr"
TASK_EMBED = "embed"
TASK_CLEANUP = "cleanup"
TASK_TYPES = (TASK_PARSE, TASK_OCR, TASK_EMBED, TASK_CLEANUP)

STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"

LEASE_EXPIRED_ERROR = "租约过期：Worker 可能已崩溃，或任务卡住未能续租"

# 失败原因可能是一长串异常信息，只保留开头，避免把任务表撑大
_MAX_ERROR_CHARS = 4000


@dataclass(frozen=True)
class Task:
    """一个已被领取的任务。"""

    id: uuid.UUID
    task_type: str
    document_id: uuid.UUID
    payload: dict[str, Any]
    # 包含本次在内的尝试次数（第一次领取时为 1）
    attempts: int
    max_attempts: int


# 被回收或失败的任务去向：还有重试机会 → pending，否则 → failed。
# 两处 UPDATE 共用这一段，保证“租约过期”和“处理函数报错”遵循同一条规则。
_RELEASE_SET = f"""
    status = CASE WHEN attempts < max_attempts AND %(retryable)s
                  THEN '{STATUS_PENDING}' ELSE '{STATUS_FAILED}' END,
    finished_at = CASE WHEN attempts < max_attempts AND %(retryable)s
                       THEN NULL ELSE now() END,
    error = %(error)s,
    lease_expires_at = NULL,
    claimed_by = NULL
"""

_RECLAIM_SQL = f"""
UPDATE processing_tasks SET {_RELEASE_SET}
WHERE id IN (
    SELECT id FROM processing_tasks
    WHERE status = '{STATUS_PROCESSING}' AND lease_expires_at < now()
    -- 多个 Worker 同时回收时各拿各的行，不互相等待，也不会按不同顺序加锁而死锁
    FOR UPDATE SKIP LOCKED
)
"""

_CLAIM_SQL = f"""
UPDATE processing_tasks SET
    status = '{STATUS_PROCESSING}',
    attempts = attempts + 1,
    claimed_by = %(worker_id)s,
    lease_expires_at = now() + make_interval(secs => %(lease_seconds)s::double precision),
    started_at = now(),
    finished_at = NULL
WHERE id = (
    SELECT id FROM processing_tasks
    WHERE status = '{STATUS_PENDING}' AND task_type = ANY(%(task_types)s::text[])
    ORDER BY created_at, id
    LIMIT 1
    -- 已被别的 Worker 锁住（正在领取）的行直接跳过：两个 Worker 不会领到同一个任务，也不互相阻塞
    FOR UPDATE SKIP LOCKED
)
RETURNING id, task_type, document_id, payload, attempts, max_attempts
"""

# 只有“仍由我领取且在处理中”的任务才能被续租或回写（约定 2）
_OWNED = f"id = %(task_id)s AND claimed_by = %(worker_id)s AND status = '{STATUS_PROCESSING}'"

_RENEW_SQL = f"""
UPDATE processing_tasks
SET lease_expires_at = now() + make_interval(secs => %(lease_seconds)s::double precision)
WHERE {_OWNED}
"""

_COMPLETE_SQL = f"""
UPDATE processing_tasks SET
    status = '{STATUS_SUCCEEDED}',
    finished_at = now(),
    error = NULL,
    lease_expires_at = NULL
WHERE {_OWNED}
"""

_FAIL_SQL = f"""
UPDATE processing_tasks SET {_RELEASE_SET}
WHERE {_OWNED}
RETURNING status
"""


def reclaim_expired(conn: psycopg.Connection) -> int:
    """回收租约已过期但仍为 processing 的任务，返回回收的数量。"""
    with conn.transaction():
        cur = conn.execute(_RECLAIM_SQL, {"error": LEASE_EXPIRED_ERROR, "retryable": True})
        return cur.rowcount


def claim(
    conn: psycopg.Connection,
    *,
    worker_id: str,
    task_types: Sequence[str],
    lease_seconds: float,
) -> Task | None:
    """领取一个最早创建的 pending 任务；没有可领取的任务时返回 None。

    领取前先回收过期租约，所以不需要单独的回收进程：只要还有 Worker 在领任务，
    崩溃的 Worker 留下的任务就会被重新放回队列。
    """
    reclaim_expired(conn)
    if not task_types:
        return None
    with conn.transaction():
        row = conn.execute(
            _CLAIM_SQL,
            {
                "worker_id": worker_id,
                "task_types": list(task_types),
                "lease_seconds": lease_seconds,
            },
        ).fetchone()
    if row is None:
        return None
    return Task(
        id=row[0],
        task_type=row[1],
        document_id=row[2],
        payload=row[3],
        attempts=row[4],
        max_attempts=row[5],
    )


def renew(
    conn: psycopg.Connection, *, task_id: uuid.UUID, worker_id: str, lease_seconds: float
) -> bool:
    """续租。返回 False 表示任务已不归本 Worker 所有（租约被回收），应立即停止处理。"""
    with conn.transaction():
        cur = conn.execute(
            _RENEW_SQL,
            {"task_id": task_id, "worker_id": worker_id, "lease_seconds": lease_seconds},
        )
        return cur.rowcount == 1


def complete(conn: psycopg.Connection, *, task_id: uuid.UUID, worker_id: str) -> bool:
    """标记成功。返回 False 表示任务已不归本 Worker 所有，本次结果未被记录。"""
    with conn.transaction():
        cur = conn.execute(_COMPLETE_SQL, {"task_id": task_id, "worker_id": worker_id})
        return cur.rowcount == 1


def fail(
    conn: psycopg.Connection,
    *,
    task_id: uuid.UUID,
    worker_id: str,
    error: str,
    retryable: bool = True,
) -> str | None:
    """记录一次失败并保存原因。

    返回任务的新状态：还有重试机会时为 "pending"，否则为 "failed"；
    返回 None 表示任务已不归本 Worker 所有，本次失败未被记录。
    retryable=False 用于重试也没有意义的失败（例如文件本身是畸形的），直接标记 failed。
    """
    with conn.transaction():
        row = conn.execute(
            _FAIL_SQL,
            {
                "task_id": task_id,
                "worker_id": worker_id,
                "error": error[:_MAX_ERROR_CHARS],
                "retryable": retryable,
            },
        ).fetchone()
    return row[0] if row else None
