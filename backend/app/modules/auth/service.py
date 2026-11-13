"""M1：账号的创建与登录校验。"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import InvalidCredentialsError, UsernameTakenError
from app.core.security import hash_password, verify_password
from app.db.models import User

# 用户不存在时也对着它做一次完整的哈希验证，
# 让“用户名不存在”和“密码错误”耗时接近，不能靠响应时间探测某个用户名是否已注册。
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def create_user(session: Session, username: str, password: str, *, role: str = "user") -> User:
    """创建账号并提交。用户名已存在时抛 UsernameTakenError。

    调用方负责先校验用户名、密码的格式（schemas.RegisterRequest）。
    """
    user = User(username=username, password_hash=hash_password(password), role=role)
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        # 靠数据库的唯一约束判断重名，而不是先查再插：两个并发注册不会都成功
        session.rollback()
        raise UsernameTakenError("用户名已存在") from exc
    return user


def authenticate(session: Session, username: str, password: str) -> User:
    """校验用户名和密码。失败时抛 InvalidCredentialsError，不区分是哪一个错。"""
    user = session.scalar(select(User).where(User.username == username))
    password_ok = verify_password(password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not password_ok:
        raise InvalidCredentialsError("用户名或密码错误")
    return user
