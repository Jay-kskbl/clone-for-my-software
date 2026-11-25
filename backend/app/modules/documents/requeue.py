"""把失败的 embed、ocr 任务成批放回队列（T24ae，D56）。

用在一段较长的故障之后，例如 CLIP 服务关了几个小时：期间的任务按重试间隔（T24ad）试完 3 次
就是 failed，服务恢复后也不会自己再试。单个任务可以用 POST /api/tasks/{id}/retry；这里是批量的。

不包括 parse：它失败时文档状态也是 failed，多数是文件本身的问题，逐个看过再重试更合适。
"""

import uuid
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from shared.tasks import STATUS_FAILED, STATUS_PENDING, TASK_EMBED, TASK_OCR
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import Document, ProcessingTask

REQUEUE_TYPES = (TASK_EMBED, TASK_OCR)

# 报告里一条失败原因最多显示多少个字符
_REASON_CHARS = 100


@dataclass(frozen=True)
class FailedTask:
    """一个失败的任务，连同判断能否重做所需要的文档信息。"""

    id: uuid.UUID
    task_type: str
    document_id: uuid.UUID
    payload: dict[str, Any] | None
    error: str | None
    document_deleted: bool
    parse_version: str | None


@dataclass(frozen=True)
class RequeuePlan:
    tasks: tuple[FailedTask, ...] = ()
    # 跳过的数量：文档已删除；OCR 任务属于旧的解析版本（OCR Worker 领到也会跳过）
    skipped_deleted: int = 0
    skipped_old_version: int = 0

    @property
    def document_count(self) -> int:
        return len({task.document_id for task in self.tasks})

    def reasons(self) -> list[tuple[str, int]]:
        """失败原因和数量，多的在前。"""
        counter = Counter(_reason(task.error) for task in self.tasks)
        return sorted(counter.items(), key=lambda item: (-item[1], item[0]))


def _reason(error: str | None) -> str:
    lines = (error or "").strip().splitlines()
    if not lines:
        return "（没有记录原因）"
    first = lines[0]
    return first if len(first) <= _REASON_CHARS else first[:_REASON_CHARS] + "…"


def plan_requeue(tasks: Iterable[FailedTask]) -> RequeuePlan:
    """从失败的任务里挑出重做有意义的。纯函数。"""
    selected: list[FailedTask] = []
    deleted = old_version = 0
    for task in tasks:
        if task.document_deleted:
            deleted += 1
        elif task.task_type == TASK_OCR and (
            task.parse_version is None
            or (task.payload or {}).get("parse_version") != task.parse_version
        ):
            old_version += 1
        else:
            selected.append(task)
    return RequeuePlan(tuple(selected), deleted, old_version)


def load_failed_tasks(session: Session, task_type: str) -> list[FailedTask]:
    rows = session.execute(
        select(
            ProcessingTask.id,
            ProcessingTask.task_type,
            ProcessingTask.document_id,
            ProcessingTask.payload,
            ProcessingTask.error,
            Document.deleted_at,
            Document.parse_version,
        )
        .join(Document, Document.id == ProcessingTask.document_id)
        .where(ProcessingTask.status == STATUS_FAILED, ProcessingTask.task_type == task_type)
        .order_by(ProcessingTask.created_at, ProcessingTask.id)
    )
    return [
        FailedTask(
            id=row.id,
            task_type=row.task_type,
            document_id=row.document_id,
            payload=row.payload,
            error=row.error,
            document_deleted=row.deleted_at is not None,
            parse_version=row.parse_version,
        )
        for row in rows
    ]


def requeue(session: Session, plan: RequeuePlan) -> int:
    """放回队列，尝试次数清零，返回实际放回的数量。重做是覆盖，不会叠加（GLOBAL §3.3 幂等）。"""
    if not plan.tasks:
        return 0
    result = session.execute(
        update(ProcessingTask)
        # 条件更新：列出之后状态变了的任务（例如有人同时重试了它）不动
        .where(
            ProcessingTask.id.in_([task.id for task in plan.tasks]),
            ProcessingTask.status == STATUS_FAILED,
        )
        # 与 retry_task、reocr 清空同样的列；started_at 清空后不受重试间隔限制，马上能领
        .values(
            status=STATUS_PENDING,
            attempts=0,
            error=None,
            started_at=None,
            finished_at=None,
            lease_expires_at=None,
            claimed_by=None,
        )
        .execution_options(synchronize_session=False)
    )
    session.commit()
    return result.rowcount
