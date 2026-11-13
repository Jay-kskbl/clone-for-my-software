"""任务接口（docs/api.md §6）：查看文档的处理任务、重试失败的任务、管理员查看全部任务。"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AdminUser, CurrentUser, PaginationDep, SessionDep
from app.modules.auth.permissions import get_accessible_document
from app.modules.documents import tasks
from app.modules.documents.schemas import Status, TaskList, TaskOut, TaskPage

router = APIRouter(prefix="/api", tags=["tasks"])


@router.get("/documents/{document_id}/tasks", response_model=TaskList)
def list_document_tasks(document_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> TaskList:
    document = get_accessible_document(session, user, document_id)
    items = tasks.list_document_tasks(session, document)
    return TaskList(items=[TaskOut.model_validate(t) for t in items])


@router.post("/tasks/{task_id}/retry", response_model=TaskOut)
def retry_task(task_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> TaskOut:
    return TaskOut.model_validate(tasks.retry_task(session, user, task_id))


@router.get("/tasks", response_model=TaskPage)
def list_all_tasks(
    _admin: AdminUser,
    session: SessionDep,
    pagination: PaginationDep,
    status: Status | None = None,
    task_type: Annotated[str | None, Query(max_length=32)] = None,
) -> TaskPage:
    items, total = tasks.list_all_tasks(
        session,
        page=pagination.page,
        page_size=pagination.page_size,
        status=status,
        task_type=task_type,
    )
    return TaskPage(
        items=[TaskOut.model_validate(t) for t in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )
