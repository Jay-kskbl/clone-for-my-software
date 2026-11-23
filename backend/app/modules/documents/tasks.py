"""任务的查看与人工重试（docs/api.md §6）。任务的领取和执行在 shared/tasks.py 与 app/worker。"""

import uuid

from shared.tasks import STATUS_FAILED, STATUS_PENDING, TASK_PARSE
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError, TaskNotRetryableError
from app.db.models import Document, ProcessingTask, User
from app.modules.auth.permissions import ADMIN_ROLE
from app.modules.documents.schemas import TaskOut
from app.modules.documents.task_errors import public_task_error


def to_task_out(user: User, task: ProcessingTask) -> TaskOut:
    """对外的任务信息。失败原因的原文只给管理员看，其他人看清理过的（task_errors.py）。"""
    out = TaskOut.model_validate(task)
    if user.role == ADMIN_ROLE:
        return out
    return out.model_copy(update={"error": public_task_error(out.error)})


def list_document_tasks(session: Session, document: Document) -> list[ProcessingTask]:
    return list(
        session.scalars(
            select(ProcessingTask)
            .where(ProcessingTask.document_id == document.id)
            .order_by(ProcessingTask.created_at.desc(), ProcessingTask.id)
        )
    )


def list_all_tasks(
    session: Session,
    *,
    page: int,
    page_size: int,
    status: str | None = None,
    task_type: str | None = None,
) -> tuple[list[ProcessingTask], int]:
    """全部任务（管理员用），包括已软删除文档的清理任务。"""
    conditions = []
    if status is not None:
        conditions.append(ProcessingTask.status == status)
    if task_type is not None:
        conditions.append(ProcessingTask.task_type == task_type)

    total = session.scalar(select(func.count()).select_from(ProcessingTask).where(*conditions)) or 0
    items = session.scalars(
        select(ProcessingTask)
        .where(*conditions)
        .order_by(ProcessingTask.created_at.desc(), ProcessingTask.id)
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    return list(items), total


def retry_task(session: Session, user: User, task_id: uuid.UUID) -> ProcessingTask:
    """把一个 failed 的任务放回队列，尝试次数清零。

    权限：任务所属文档的 owner 或管理员。文档已被软删除时（此时只剩清理任务有意义），
    只有管理员能重试；对其他人来说这个文档已经不存在，返回 404。
    """
    task = session.get(ProcessingTask, task_id)
    if task is None:
        raise NotFoundError("任务不存在")

    document = session.get(Document, task.document_id)
    is_admin = user.role == ADMIN_ROLE
    if document is None or (document.deleted_at is not None and not is_admin):
        raise NotFoundError("任务不存在")
    if not is_admin and document.owner_id != user.id:
        # 被共享者能看到任务，但不能重试；完全无权访问的人同样是 403
        raise ForbiddenError("只有文档的 owner 可以重试任务")

    # 条件更新：只有此刻仍为 failed 的任务才会被放回队列。
    # 两个人同时点重试，或状态刚好变化时，不会把正在处理或已成功的任务重置掉。
    result = session.execute(
        update(ProcessingTask)
        .where(ProcessingTask.id == task_id, ProcessingTask.status == STATUS_FAILED)
        .values(
            status=STATUS_PENDING,
            attempts=0,
            error=None,
            started_at=None,
            finished_at=None,
            lease_expires_at=None,
            claimed_by=None,
        )
    )
    if result.rowcount != 1:
        session.rollback()
        raise TaskNotRetryableError("只有失败的任务可以重试")
    if task.task_type == TASK_PARSE:
        # 文档状态跟随它的 parse 任务：任务回到队列，文档也回到“等待处理”。
        # 只改 failed 的文档：已软删除的文档状态无所谓，改了也不影响任何查询
        session.execute(
            update(Document)
            .where(Document.id == task.document_id, Document.status == STATUS_FAILED)
            .values(status=STATUS_PENDING)
        )
    session.commit()
    session.refresh(task)
    return task
