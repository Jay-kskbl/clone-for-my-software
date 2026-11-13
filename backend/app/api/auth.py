"""认证接口（docs/api.md §4）：注册、登录、查看当前用户。"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep, SettingsDep
from app.core.security import create_access_token
from app.modules.auth.schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.modules.auth.service import authenticate, create_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


# 用普通 def：数据库访问和密码哈希都是阻塞操作，FastAPI 会放到线程池里执行
@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterRequest, session: SessionDep) -> UserOut:
    # 接口只能创建普通用户；管理员由命令行创建（decisions.md D12）
    user = create_user(session, body.username, body.password)
    return UserOut.model_validate(user)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, session: SessionDep, settings: SettingsDep) -> TokenResponse:
    user = authenticate(session, body.username, body.password)
    token = create_access_token(
        user.id,
        secret=settings.jwt_secret.get_secret_value(),
        expires_in_seconds=settings.access_token_expire_seconds,
    )
    return TokenResponse(access_token=token, expires_in=settings.access_token_expire_seconds)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
