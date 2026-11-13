"""M1 认证与权限：账号、登录校验、文档访问权限判断。"""

from app.modules.auth.permissions import (
    accessible_document_ids,
    accessible_filter,
    can_access,
    get_accessible_document,
)
from app.modules.auth.service import authenticate, create_user

__all__ = [
    "accessible_document_ids",
    "accessible_filter",
    "authenticate",
    "can_access",
    "create_user",
    "get_accessible_document",
]
