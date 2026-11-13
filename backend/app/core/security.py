"""密码哈希与登录令牌。纯函数，不访问数据库，不读取全局配置。"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# Argon2id，参数用 argon2-cffi 的默认值（RFC 9106 的低内存推荐配置）。
# 哈希串里自带算法、参数和盐，所以以后调整参数不影响已有账号的验证。
_hasher = PasswordHasher()

# 只签发、只接受这一种算法：解码时写死算法列表，
# 防止令牌头里自称 alg=none 或换成别的算法来绕过签名校验。
_JWT_ALGORITHM = "HS256"


class InvalidTokenError(Exception):
    """令牌缺失必要字段、签名不对、已过期或格式错误。"""


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        # 密码不匹配，或数据库里存的不是合法的哈希串：都算验证失败
        return False


def create_access_token(
    user_id: uuid.UUID, *, secret: str, expires_in_seconds: int, now: datetime | None = None
) -> str:
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": issued_at,
        "exp": issued_at + timedelta(seconds=expires_in_seconds),
    }
    return jwt.encode(payload, secret, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str, *, secret: str) -> uuid.UUID:
    """校验令牌并返回其中的 user_id；任何问题都抛 InvalidTokenError。"""
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[_JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise InvalidTokenError(type(exc).__name__) from exc
