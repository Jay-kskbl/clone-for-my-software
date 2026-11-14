"""文档接口（docs/api.md §5）：上传、列表、详情、下载、删除、共享、标签。"""

import logging
import uuid
from collections.abc import Iterator
from typing import Annotated, BinaryIO
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import (
    CurrentUser,
    PaginationDep,
    SessionDep,
    SettingsDep,
    StorageDep,
    TextIndexDep,
)
from app.core.errors import AppError
from app.db.models import Document
from app.modules.auth.permissions import get_accessible_document, get_owned_document
from app.modules.documents import service, sharing
from app.modules.documents.schemas import (
    DocumentOut,
    DocumentPage,
    Scope,
    ShareList,
    ShareOut,
    ShareRequest,
    Status,
    TagList,
    TagsRequest,
)
from app.modules.documents.tags import (
    list_visible_tags,
    normalize_tags,
    replace_document_tags,
    tags_by_document,
)
from app.modules.storage import StoredFileNotFoundError
from app.modules.text_index import (
    OpenSearchClient,
    TextIndexError,
    ensure_indices,
    index_doc_meta,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["documents"])

_DOWNLOAD_CHUNK_BYTES = 1024 * 1024


# 本文件的路由都用普通 def：数据库和文件操作是阻塞的，FastAPI 会放到线程池里执行


@router.post("/documents", response_model=DocumentOut, status_code=201)
def upload_document(
    user: CurrentUser,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    tags: Annotated[list[str] | None, Form()] = None,
) -> DocumentOut:
    document = service.upload_document(
        session,
        storage,
        user,
        stream=file.file,
        filename=file.filename,
        tags=tags or [],
        limits=service.UploadLimits(
            max_bytes=settings.upload_max_bytes,
            max_filename_chars=settings.upload_max_filename_chars,
            allowed_extensions=settings.upload_allowed_extensions,
        ),
    )
    return service.to_document_out(session, user, [document])[0]


@router.get("/documents", response_model=DocumentPage)
def list_documents(
    user: CurrentUser,
    session: SessionDep,
    pagination: PaginationDep,
    status: Status | None = None,
    tag: Annotated[str | None, Query(max_length=64)] = None,
    scope: Scope | None = None,
) -> DocumentPage:
    documents, total = service.list_documents(
        session,
        user,
        page=pagination.page,
        page_size=pagination.page_size,
        status=status,
        tag=tag,
        scope=scope,
    )
    return DocumentPage(
        items=service.to_document_out(session, user, documents),
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> DocumentOut:
    document = get_accessible_document(session, user, document_id)
    return service.to_document_out(session, user, [document])[0]


def _iter_file(f: BinaryIO) -> Iterator[bytes]:
    try:
        while chunk := f.read(_DOWNLOAD_CHUNK_BYTES):
            yield chunk
    finally:
        f.close()


def _content_disposition(filename: str) -> str:
    """生成下载用的 Content-Disposition。

    HTTP 头只能放 ASCII：filename= 给一个去掉非 ASCII 字符的后备名字，
    filename*= 按 RFC 5987 用百分号编码携带完整的原始文件名（中文文件名靠它）。
    """
    fallback = "".join(ch if " " <= ch < "\x7f" and ch not in '"\\' else "_" for ch in filename)
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


@router.get("/documents/{document_id}/download")
def download_document(
    document_id: uuid.UUID, user: CurrentUser, session: SessionDep, storage: StorageDep
) -> StreamingResponse:
    document = get_accessible_document(session, user, document_id)
    try:
        f = storage.open(document.storage_key)
    except StoredFileNotFoundError:
        # 数据库有记录而文件不在：属于数据不一致（M13 负责发现），不是“文档不存在”
        logger.error("文档 %s 的文件在存储中缺失", document.id)
        raise AppError("文件暂时无法读取") from None

    return StreamingResponse(
        _iter_file(f),
        media_type=document.mime_type,
        headers={
            "Content-Length": str(document.size_bytes),
            "Content-Disposition": _content_disposition(document.filename),
            # 类型是服务端按文件内容识别的，不让浏览器再自行猜测
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> Response:
    document = get_owned_document(session, user, document_id)
    service.soft_delete_document(session, document)
    return Response(status_code=204)


# ---- 共享 ----


@router.get("/documents/{document_id}/shares", response_model=ShareList)
def list_shares(document_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> ShareList:
    document = get_owned_document(session, user, document_id)
    return ShareList(items=sharing.list_shares(session, document))


@router.post("/documents/{document_id}/shares", response_model=ShareOut, status_code=201)
def add_share(
    document_id: uuid.UUID,
    body: ShareRequest,
    user: CurrentUser,
    session: SessionDep,
    response: Response,
) -> ShareOut:
    document = get_owned_document(session, user, document_id)
    share, created = sharing.add_share(session, document, body.username)
    if not created:
        # 已经共享过：返回已有记录和 200，而不是 201
        response.status_code = 200
    return share


@router.delete("/documents/{document_id}/shares/{user_id}", status_code=204)
def remove_share(
    document_id: uuid.UUID, user_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Response:
    document = get_owned_document(session, user, document_id)
    sharing.remove_share(session, document, user_id)
    return Response(status_code=204)


# ---- 标签 ----


@router.put("/documents/{document_id}/tags", response_model=DocumentOut)
def set_tags(
    document_id: uuid.UUID,
    body: TagsRequest,
    user: CurrentUser,
    session: SessionDep,
    text_index: TextIndexDep,
) -> DocumentOut:
    document = get_owned_document(session, user, document_id)
    replace_document_tags(session, document.id, normalize_tags(body.tags))
    session.commit()
    _sync_doc_meta(session, text_index, document)
    return service.to_document_out(session, user, [document])[0]


def _sync_doc_meta(session: Session, text_index: OpenSearchClient, document: Document) -> None:
    """标签改动后，把文件名和最新的标签写进 doc_meta 索引，这样按标签检索能立刻反映改动。

    数据库是标签的唯一依据，这里只是让索引跟上。检索服务此刻不可用时不让改标签失败：
    记一条警告，索引暂时是旧的，之后由重新解析或一致性检查（T18）补上。
    """
    tags = tags_by_document(session, [document.id]).get(document.id, [])
    try:
        # 先保证索引按项目的 mapping 建好。否则往一个还不存在的索引里写数据，
        # OpenSearch 可能自动建一个结构不对的索引（没有中文分词），之后只能删掉重建
        ensure_indices(text_index)
        index_doc_meta(text_index, document_id=document.id, filename=document.filename, tags=tags)
    except TextIndexError as exc:
        logger.warning("文档 %s 的标签已保存，但未能同步到检索索引（%s）", document.id, exc.message)


@router.get("/tags", response_model=TagList)
def list_tags(user: CurrentUser, session: SessionDep) -> TagList:
    return TagList(items=list_visible_tags(session, user))
