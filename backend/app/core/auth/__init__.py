"""鉴权子包 —— 对外暴露密码、JWT、依赖三组工具。"""

from app.core.auth.deps import (
    get_current_user,
    get_current_user_optional,
    require_admin,
    require_merchant,
    require_role,
)
from app.core.auth.jwt import InvalidTokenError, create_access_token, decode_token
from app.core.auth.password import hash_password, verify_password

__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_token",
    "InvalidTokenError",
    "get_current_user",
    "get_current_user_optional",
    "require_role",
    "require_admin",
    "require_merchant",
]
