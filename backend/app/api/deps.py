"""路由共用的依赖：数据库会话、当前登录用户。"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.errors import UnauthenticatedError
from app.core.security import InvalidTokenError, decode_access_token
from app.db.models import User

# auto_error=False：缺少或格式不对的 Authorization 头由下面统一转成 401 和项目的错误结构，
# 而不是 FastAPI 默认的响应。
_bearer = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session(request: Request) -> Iterator[Session]:
    """每个请求一个会话，请求结束时关闭。提交由业务代码显式执行。"""
    with request.app.state.session_factory() as session:
        yield session


SettingsDep = Annotated[Settings, Depends(get_settings)]
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
