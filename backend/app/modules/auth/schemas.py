"""认证相关的请求/响应结构（docs/api.md §4）。"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# 用户名：3–32 个字符，只允许 ASCII 字母、数字、下划线、点、连字符。
# 限制字符集是为了避免外观相同但编码不同的用户名（共享时按用户名指定对方，见 decisions.md D13）。
Username = Annotated[str, Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")]
# 密码：8–128 个字符。上限是为了限制一次哈希计算的开销。
Password = Annotated[str, Field(min_length=8, max_length=128)]


class RegisterRequest(BaseModel):
    # 禁止多余字段：请求里带 role 之类的字段会被拒绝，而不是被悄悄忽略
    model_config = ConfigDict(extra="forbid")

    username: Username
    password: Password


class LoginRequest(BaseModel):
    """登录不检查用户名、密码的格式（不对就是登录失败），只限制长度。"""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(max_length=64)
    password: str = Field(max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class UserOut(BaseModel):
    """对外的用户信息。没有 password_hash 字段，所以任何接口都不可能把它返回出去。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    role: Literal["user", "admin"]
    created_at: datetime
