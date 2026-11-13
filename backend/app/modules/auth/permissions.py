"""M1：文档访问权限（GLOBAL §7.1，附录 A11）。

规则只有三条：owner 可访问自己的文档；管理员可访问全部；被共享者可访问共享给自己的文档。
已软删除的文档对所有人（包括管理员）不可访问（GLOBAL §4.5）。

每次调用都查数据库、不做缓存：取消共享、删除文档之后，下一次判断立即生效。
"""

import uuid

from sqlalchemy import ColumnElement, and_, exists, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError
from app.db.models import Document, DocumentShare, User

ADMIN_ROLE = "admin"


def accessible_filter(user: User) -> ColumnElement[bool]:
    """用于 Document 查询的 WHERE 条件：只保留 user 可访问且未删除的文档。

    文档列表（T08）和检索的二次校验（T15）都用这同一个条件，权限规则只写在这里一处。
    """
    not_deleted = Document.deleted_at.is_(None)
    if user.role == ADMIN_ROLE:
        return not_deleted
    shared_to_user = select(DocumentShare.document_id).where(DocumentShare.user_id == user.id)
    return and_(
        not_deleted,
        or_(Document.owner_id == user.id, Document.id.in_(shared_to_user)),
    )


def accessible_document_ids(session: Session, user: User) -> set[uuid.UUID]:
    """user 当前可访问的全部 document_id。"""
    return set(session.scalars(select(Document.id).where(accessible_filter(user))))


def can_access(session: Session, user: User, doc: Document) -> bool:
    """user 是否可以读取、检索 doc。"""
    if doc.deleted_at is not None:
        return False
    if user.role == ADMIN_ROLE or doc.owner_id == user.id:
        return True
    return bool(
        session.scalar(
            select(
                exists().where(
                    DocumentShare.document_id == doc.id, DocumentShare.user_id == user.id
                )
            )
        )
    )


def get_accessible_document(session: Session, user: User, document_id: uuid.UUID) -> Document:
    """按 ID 取一个 user 可访问的文档。

    不存在或已删除 → NotFoundError（404）；存在但无权访问 → ForbiddenError（403）。
    （docs/api.md §1.1）
    """
    doc = session.get(Document, document_id)
    if doc is None or doc.deleted_at is not None:
        raise NotFoundError("文档不存在")
    if not can_access(session, user, doc):
        raise ForbiddenError("无权访问该文档")
    return doc
