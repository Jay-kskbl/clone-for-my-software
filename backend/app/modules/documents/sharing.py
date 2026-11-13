"""文档共享：owner 把文档共享给指定用户（附录 A11，docs/api.md §5.8）。"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, RequestInvalidError
from app.db.models import Document, DocumentShare, User
from app.modules.documents.schemas import ShareOut, UserRef


def _share_out(share: DocumentShare, user: User) -> ShareOut:
    return ShareOut(user=UserRef.model_validate(user), created_at=share.created_at)


def list_shares(session: Session, document: Document) -> list[ShareOut]:
    rows = session.execute(
        select(DocumentShare, User)
        .join(User, User.id == DocumentShare.user_id)
        .where(DocumentShare.document_id == document.id)
        .order_by(DocumentShare.created_at, User.username)
    )
    return [_share_out(share, user) for share, user in rows]


def add_share(session: Session, document: Document, username: str) -> tuple[ShareOut, bool]:
    """把 document 共享给 username。返回（共享记录，是否是新建的）。

    已经共享过时返回已有记录，不报错。按用户名指定对方（decisions.md D13）。
    """
    target = session.scalar(select(User).where(User.username == username))
    if target is None:
        raise NotFoundError("用户不存在")
    if target.id == document.owner_id:
        raise RequestInvalidError("不能把文档共享给它的 owner")

    key = (document.id, target.id)
    existing = session.get(DocumentShare, key)
    if existing is not None:
        return _share_out(existing, target), False

    share = DocumentShare(document_id=document.id, user_id=target.id)
    session.add(share)
    try:
        session.commit()
    except IntegrityError:
        # 两个相同的请求同时到达：另一个已经插入了这一行，按“已共享”返回
        session.rollback()
        existing = session.get(DocumentShare, key)
        if existing is None:
            raise
        return _share_out(existing, target), False
    return _share_out(share, target), True


def remove_share(session: Session, document: Document, user_id: uuid.UUID) -> None:
    """取消共享。提交后对方立即无法访问和检索该文档（权限判断每次都查数据库）。"""
    share = session.get(DocumentShare, (document.id, user_id))
    if share is None:
        raise NotFoundError("没有这条共享记录")
    session.delete(share)
    session.commit()
