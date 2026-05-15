"""JWT 签发与解码 —— HS256 默认,生产可换 RS256。

设计:
- payload 只放 user_id 和 role,其它字段从 DB 实时读,避免角色变更不生效
- exp 字段用 Unix 时间戳,客户端不需要本地时区
- 解码失败一律抛 InvalidTokenError,在 dependency 层转 401
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from config import settings


class InvalidTokenError(Exception):
    """JWT 无效 —— 过期、签名错、格式错都走这个异常,上层统一返 401。"""


def create_access_token(user_id: int, role: str, extra: dict[str, Any] | None = None) -> str:
    """签发 access token。"""
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.auth.jwt_access_ttl_minutes)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(
        payload,
        settings.auth.jwt_secret.get_secret_value(),
        algorithm=settings.auth.jwt_algorithm,
    )


def decode_token(token: str) -> dict[str, Any]:
    """解码 token —— 失败抛 InvalidTokenError。"""
    try:
        return jwt.decode(
            token,
            settings.auth.jwt_secret.get_secret_value(),
            algorithms=[settings.auth.jwt_algorithm],
        )
    except JWTError as e:
        raise InvalidTokenError(str(e)) from e
