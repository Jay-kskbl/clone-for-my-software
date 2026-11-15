"""抽取文本接口（docs/api.md §5.6）：GET /api/documents/{id}/text。

返回文档当前解析版本的文本片段，供 Word、Excel 的文本预览（附录 A16），
以及从检索结果跳到命中的位置。数据来自数据库的 document_chunks 表，不查 OpenSearch：
检索服务不可用时仍能预览。
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from shared.contracts import SourceLocator, SourceType
from shared.ids import parse_chunk_id
from sqlalchemy import func, select

from app.api.deps import CurrentUser, PaginationDep, SessionDep
from app.core.errors import RequestInvalidError
from app.db.models import DocumentChunk
from app.modules.auth.permissions import get_accessible_document

router = APIRouter(prefix="/api", tags=["documents"])


class TextChunkOut(BaseModel):
    chunk_id: str
    seq: int
    source_type: SourceType
    text: str
    locator: SourceLocator


class TextPage(BaseModel):
    items: list[TextChunkOut]
    total: int
    page: int
    page_size: int


def _page_containing(
    session, base_filter: list[Any], chunk_id: str, document_id: uuid.UUID, page_size: int
) -> int:
    """chunk_id 所在的页码（从 1 开始）。片段不属于这个文档或不在当前版本时报 422。"""
    try:
        parts = parse_chunk_id(chunk_id)
    except ValueError as exc:
        raise RequestInvalidError("chunk_id 格式不正确") from exc
    if parts.document_id != document_id:
        raise RequestInvalidError("chunk_id 不属于这个文档")
    exists = session.scalar(
        select(func.count())
        .select_from(DocumentChunk)
        .where(*base_filter, DocumentChunk.chunk_id == chunk_id)
    )
    if not exists:
        # 文档被重新解析过，检索结果里的片段已经不是当前版本了；从第一页开始看
        return 1
    before = session.scalar(
        select(func.count())
        .select_from(DocumentChunk)
        .where(*base_filter, DocumentChunk.seq < parts.seq)
    )
    return before // page_size + 1


@router.get("/documents/{document_id}/text", response_model=TextPage)
def get_document_text(
    document_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    pagination: PaginationDep,
    source_type: SourceType | None = None,
    chunk_id: Annotated[str | None, Query(max_length=256)] = None,
) -> TextPage:
    """chunk_id：指定后忽略 page，直接返回这个片段所在的那一页（从检索结果跳转时用）。"""
    document = get_accessible_document(session, user, document_id)
    page_size = pagination.page_size
    if document.parse_version is None:
        # 还没有解析成功：返回空列表，前端结合 Document.status 提示
        return TextPage(items=[], total=0, page=pagination.page, page_size=page_size)

    base_filter: list[Any] = [
        DocumentChunk.document_id == document.id,
        # 只看当前生效的版本：重新解析期间新旧版本可能短暂共存
        DocumentChunk.parse_version == document.parse_version,
    ]
    if source_type is not None:
        base_filter.append(DocumentChunk.source_type == source_type)

    page = pagination.page
    if chunk_id is not None:
        page = _page_containing(session, base_filter, chunk_id, document.id, page_size)

    total = session.scalar(select(func.count()).select_from(DocumentChunk).where(*base_filter))
    rows = session.scalars(
        select(DocumentChunk)
        .where(*base_filter)
        .order_by(DocumentChunk.seq)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return TextPage(
        items=[
            TextChunkOut(
                chunk_id=row.chunk_id,
                seq=row.seq,
                source_type=row.source_type,
                text=row.text,
                locator=row.locator,
            )
            for row in rows
        ],
        total=total or 0,
        page=page,
        page_size=page_size,
    )
