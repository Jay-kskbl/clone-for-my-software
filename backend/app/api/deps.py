"""路由共用的依赖：数据库会话、当前登录用户。"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from shared.text_index import OpenSearchClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.errors import ForbiddenError, UnauthenticatedError
from app.core.security import InvalidTokenError, decode_access_token
from app.db.models import User
from app.modules.auth.permissions import ADMIN_ROLE
from app.modules.clip import ClipClient
from app.modules.storage import LocalStorage

# auto_error=False：缺少或格式不对的 Authorization 头由下面统一转成 401 和项目的错误结构，
# 而不是 FastAPI 默认的响应。
_bearer = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session(request: Request) -> Iterator[Session]:
    """每个请求一个会话，请求结束时关闭。提交由业务代码显式执行。"""
    with request.app.state.session_factory() as session:
        yield session


def get_storage(request: Request) -> LocalStorage:
    return request.app.state.storage


def get_text_index(request: Request) -> OpenSearchClient:
    return request.app.state.text_index


def get_query_clip(request: Request) -> ClipClient:
    """检索用的 CLIP 客户端（编码查询文本，超时短）。"""
    return request.app.state.query_clip


SettingsDep = Annotated[Settings, Depends(get_settings)]
StorageDep = Annotated[LocalStorage, Depends(get_storage)]
TextIndexDep = Annotated[OpenSearchClient, Depends(get_text_index)]
QueryClipDep = Annotated[ClipClient, Depends(get_query_clip)]
SessionDep = Annotated[Session, Depends(get_session)]


def current_user(
    settings: SettingsDep,
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """从 Authorization: Bearer <token> 得到当前用户；任何问题都是 401 UNAUTHENTICATED。

    令牌里只有 user_id。角色每次都从数据库读，所以账号被删除或角色变化后立即生效，
    不必等令牌过期。
    """
    if credentials is None:
        raise UnauthenticatedError("未登录")
    try:
        user_id = decode_access_token(
            credentials.credentials, secret=settings.jwt_secret.get_secret_value()
        )
    except InvalidTokenError:
        raise UnauthenticatedError("令牌无效或已过期") from None

    user = session.get(User, user_id)
    if user is None:
        raise UnauthenticatedError("令牌无效或已过期")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != ADMIN_ROLE:
        raise ForbiddenError("需要管理员权限")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


class Pagination:
    """分页参数（docs/api.md §1）：page 从 1 开始，page_size 最大 100。"""

    def __init__(
        self,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> None:
        self.page = page
        self.page_size = page_size


PaginationDep = Annotated[Pagination, Depends()]
