"""M2 文档管理：上传、列表、详情、软删除（docs/api.md §5）。

上传的步骤和失败处理（GLOBAL §6.2）：

    1. 存储层把内容写到临时位置，同时计算 sha256、检查大小、按魔数识别类型
    2. 数据库：写 Document（pending）、标签、parse 任务，flush 但不提交
    3. 存储层把临时文件移动到正式路径
    4. 数据库提交

任何一步失败：数据库回滚，临时文件删除，已移动到正式路径的文件也删除。
先移动文件、后提交数据库的顺序是有意的：Worker 只能看到已提交的任务，
它看到任务时文件一定已经在正式路径上。进程恰好在第 3、4 步之间被杀掉时，
留下的是一个没有数据库记录的文件（不影响任何功能，M13 一致性检查能发现），
而不是一条指向不存在文件的数据库记录。
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import BinaryIO

from shared.tasks import TASK_CLEANUP, TASK_PARSE
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import (
    FileTooLargeError,
    RequestInvalidError,
    UnsupportedFileTypeError,
)
from app.db.models import Document, DocumentShare, DocumentTag, ProcessingTask, Tag, User
from app.modules.auth.permissions import ADMIN_ROLE, accessible_filter
from app.modules.documents.schemas import Access, DocumentOut, Scope, Status, UserRef
from app.modules.documents.tags import normalize_tags, replace_document_tags, tags_by_document
from app.modules.storage import LocalStorage, StagedFile
from app.modules.storage import errors as storage_errors

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UploadLimits:
    max_bytes: int
    max_filename_chars: int
    allowed_extensions: frozenset[str]


def clean_filename(raw: str | None, max_chars: int) -> str:
    """把客户端给的文件名整理成可以保存和展示的形式；不合法时抛 RequestInvalidError（422）。

    文件名只用于展示和检索，不参与存储路径（路径由服务端生成）。这里仍然去掉目录部分
    和控制字符：有的浏览器会带上完整路径，而控制字符会破坏下载时的响应头。
    """
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if ch >= " " and ch != "\x7f").strip()
    if not name or name in {".", ".."}:
        raise RequestInvalidError("文件名不能为空")
    if len(name) > max_chars:
        raise RequestInvalidError(f"文件名不能超过 {max_chars} 个字符")
    return name


def _stage(
    storage: LocalStorage, stream: BinaryIO, document_id: uuid.UUID, limits: UploadLimits
) -> StagedFile:
    try:
        staged = storage.stage(stream, document_id=document_id, max_size=limits.max_bytes)
    except storage_errors.EmptyFileError:
        raise RequestInvalidError("文件内容为空") from None
    except storage_errors.FileTooLargeError:
        raise FileTooLargeError(_too_large_message(limits.max_bytes)) from None
    except storage_errors.UnsupportedFileTypeError:
        raise UnsupportedFileTypeError(_unsupported_message(limits)) from None

    # 存储层识别出的类型还要在配置允许的范围内。扩展名取自存储层生成的路径，不是用户文件名
    extension = staged.storage_key.rsplit(".", 1)[-1]
    if extension not in limits.allowed_extensions:
        storage.discard(staged)
        raise UnsupportedFileTypeError(_unsupported_message(limits))
    return staged


def _too_large_message(max_bytes: int) -> str:
    return f"文件超过大小上限 {max_bytes / (1024 * 1024):g} MB"


def _unsupported_message(limits: UploadLimits) -> str:
    allowed = "、".join(sorted(limits.allowed_extensions))
    return f"不支持的文件类型。按文件内容识别，允许的类型：{allowed}"


def upload_document(
    session: Session,
    storage: LocalStorage,
    user: User,
    *,
    stream: BinaryIO,
    filename: str | None,
    tags: list[str],
    limits: UploadLimits,
) -> Document:
    """保存一个上传的文件并创建解析任务。失败时不留下文件或数据库记录。"""
    # 先做不需要读文件的检查
    clean_name = clean_filename(filename, limits.max_filename_chars)
    tag_names = normalize_tags(tags)

    document_id = uuid.uuid4()
    staged = _stage(storage, stream, document_id, limits)
    moved = False
    try:
        document = Document(
            id=document_id,
            owner_id=user.id,
            filename=clean_name,
            mime_type=staged.mime_type,
            size_bytes=staged.size,
            sha256=staged.sha256,
            storage_key=staged.storage_key,
            status="pending",
        )
        session.add(document)
        session.flush()
        replace_document_tags(session, document_id, tag_names)
        session.add(ProcessingTask(task_type=TASK_PARSE, document_id=document_id))
        session.flush()

        storage.commit(staged)
        moved = True
        session.commit()
    except BaseException:
        session.rollback()
        # commit() 自己失败时已经删掉了临时文件；这里处理其余情况。两个操作都可以重复执行
        storage.discard(staged)
        if moved:
            storage.delete(staged.storage_key)
        raise
    return document


def soft_delete_document(session: Session, document: Document) -> None:
    """软删除：写 deleted_at 并创建清理任务，一次提交（附录 A10）。

    提交之后该文档立即对列表、详情、下载、检索不可见（权限判断都排除 deleted_at 非空的文档）。
    索引、文件和数据库记录由清理任务（T14）异步删除。
    """
    document.deleted_at = datetime.now(UTC)
    session.add(ProcessingTask(task_type=TASK_CLEANUP, document_id=document.id))
    session.commit()


def list_documents(
    session: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    status: Status | None = None,
    tag: str | None = None,
    scope: Scope | None = None,
) -> tuple[list[Document], int]:
    """user 可访问的文档，按上传时间从新到旧。返回（本页文档，总数）。"""
    conditions = [accessible_filter(user)]
    if status is not None:
        conditions.append(Document.status == status)
    if scope == "mine":
        conditions.append(Document.owner_id == user.id)
    elif scope == "shared":
        shared_to_user = select(DocumentShare.document_id).where(DocumentShare.user_id == user.id)
        conditions.append(Document.id.in_(shared_to_user))
    if tag is not None:
        tagged = (
            select(DocumentTag.document_id)
            .join(Tag, Tag.id == DocumentTag.tag_id)
            .where(Tag.name == tag.strip())
        )
        conditions.append(Document.id.in_(tagged))

    total = session.scalar(select(func.count()).select_from(Document).where(*conditions)) or 0
    documents = session.scalars(
        select(Document)
        .where(*conditions)
        # id 作为第二排序键：同一时刻上传的文档翻页时顺序稳定，不会重复或漏掉
        .order_by(Document.created_at.desc(), Document.id)
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    return list(documents), total


def _access(user: User, document: Document) -> Access:
    if document.owner_id == user.id:
        return "owner"
    if user.role == ADMIN_ROLE:
        return "admin"
    return "shared"


def to_document_out(session: Session, user: User, documents: list[Document]) -> list[DocumentOut]:
    """把文档记录转换成接口的输出结构；标签和 owner 各用一次查询取齐。"""
    if not documents:
        return []
    tags = tags_by_document(session, [d.id for d in documents])
    owner_ids = {d.owner_id for d in documents}
    owners = {u.id: u for u in session.scalars(select(User).where(User.id.in_(owner_ids)))}
    return [
        DocumentOut(
            id=d.id,
            filename=d.filename,
            mime_type=d.mime_type,
            size_bytes=d.size_bytes,
            status=d.status,
            tags=tags[d.id],
            owner=UserRef.model_validate(owners[d.owner_id]),
            access=_access(user, d),
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in documents
    ]
