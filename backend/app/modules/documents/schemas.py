"""文档、共享、标签、任务接口的请求/响应结构（docs/api.md §5、§6）。"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["pending", "processing", "succeeded", "failed"]
Access = Literal["owner", "shared", "admin"]
Scope = Literal["mine", "shared"]


class UserRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str


class DocumentOut(BaseModel):
    """对外的文档信息。没有 storage_key、sha256 字段：服务器内部信息不出接口。"""

    id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    status: Status
    tags: list[str]
    owner: UserRef
    access: Access
    created_at: datetime
    updated_at: datetime


class DocumentPage(BaseModel):
    items: list[DocumentOut]
    total: int
    page: int
    page_size: int


class ShareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)


class ShareOut(BaseModel):
    user: UserRef
    created_at: datetime


class ShareList(BaseModel):
    items: list[ShareOut]


class TagsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tags: list[str]


class TagList(BaseModel):
    items: list[str]


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    task_type: str
    status: Status
    attempts: int
    max_attempts: int
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class TaskList(BaseModel):
    items: list[TaskOut]


class TaskPage(BaseModel):
    items: list[TaskOut]
    total: int
    page: int
    page_size: int
