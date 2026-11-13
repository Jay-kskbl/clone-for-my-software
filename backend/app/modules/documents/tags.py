"""标签：规范化、整体替换、列出可见标签（docs/api.md §5.9）。"""

import uuid
from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import RequestInvalidError
from app.db.models import Document, DocumentTag, Tag, User
from app.modules.auth.permissions import accessible_filter

MAX_TAG_CHARS = 64  # 与 tags.name 列的长度一致
MAX_TAGS_PER_DOCUMENT = 20


def normalize_tags(raw: Iterable[str]) -> list[str]:
    """去掉首尾空白和重复项，保持原有顺序。不合法时抛 RequestInvalidError（422）。"""
    result: list[str] = []
    for item in raw:
        name = item.strip()
        if not name:
            raise RequestInvalidError("标签不能为空")
        if len(name) > MAX_TAG_CHARS:
            raise RequestInvalidError(f"单个标签不能超过 {MAX_TAG_CHARS} 个字符")
        if any(ch < " " or ch == "\x7f" for ch in name):
            raise RequestInvalidError("标签不能包含控制字符")
        if name not in result:
            result.append(name)
    if len(result) > MAX_TAGS_PER_DOCUMENT:
        raise RequestInvalidError(f"一个文档最多 {MAX_TAGS_PER_DOCUMENT} 个标签")
    return result


def replace_document_tags(session: Session, document_id: uuid.UUID, names: list[str]) -> None:
    """把文档的标签整体替换为 names（已规范化）。不提交，由调用方提交。

    不存在的标签自动创建。标签名全局唯一，两个请求同时创建同一个标签时，
    ON CONFLICT DO NOTHING 让后到的那个直接复用已有的行，而不是报唯一约束错误。
    """
    session.execute(delete(DocumentTag).where(DocumentTag.document_id == document_id))
    if not names:
        return
    session.execute(
        insert(Tag)
        .values([{"id": uuid.uuid4(), "name": name} for name in names])
        .on_conflict_do_nothing(index_elements=[Tag.name])
    )
    tag_ids = session.scalars(select(Tag.id).where(Tag.name.in_(names))).all()
    session.execute(
        insert(DocumentTag).values(
            [{"document_id": document_id, "tag_id": tag_id} for tag_id in tag_ids]
        )
    )


def tags_by_document(session: Session, document_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    """一次查询取出多个文档各自的标签（按名称排序），避免列表页逐个文档查询。"""
    result: dict[uuid.UUID, list[str]] = {doc_id: [] for doc_id in document_ids}
    if not document_ids:
        return result
    rows = session.execute(
        select(DocumentTag.document_id, Tag.name)
        .join(Tag, Tag.id == DocumentTag.tag_id)
        .where(DocumentTag.document_id.in_(document_ids))
        .order_by(Tag.name)
    )
    for document_id, name in rows:
        result[document_id].append(name)
    return result


def list_visible_tags(session: Session, user: User) -> list[str]:
    """user 可访问的文档上用到的全部标签。看不到的文档，其标签名也不泄露。"""
    stmt = (
        select(Tag.name)
        .join(DocumentTag, DocumentTag.tag_id == Tag.id)
        .join(Document, Document.id == DocumentTag.document_id)
        .where(accessible_filter(user))
        .distinct()
        .order_by(Tag.name)
    )
    return list(session.scalars(stmt))
