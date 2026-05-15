"""FastAPI 鉴权依赖 —— 一行 Depends 就能拿到当前用户 + 角色检查。

用法:
    @router.get("/me")
    async def me(user: User = Depends(get_current_user)): ...

    @router.post("/admin/...")
    async def admin_only(user: User = Depends(require_admin)): ...
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.jwt import InvalidTokenError, decode_token
from db import User, UserRole, UserStatus, get_session

# tokenUrl 指向登录端点,Swagger UI 用它做"Authorize"按钮
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """从 Bearer token 解出当前用户 —— 失败 401,被封禁 403。"""
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="missing_token")

    try:
        payload = decode_token(token)
    except InvalidTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=f"invalid_token: {e}")

    user_id_raw = payload.get("sub")
    if not user_id_raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid_token_payload")

    user = await session.get(User, int(user_id_raw))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="user_not_found")
    if user.status == UserStatus.BANNED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="user_banned")
    return user


async def get_current_user_optional(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User | None:
    """游客也能用的接口 —— 没 token 返回 None,坏 token 也返回 None(不强制 401)。"""
    if not token:
        return None
    try:
        payload = decode_token(token)
        user = await session.get(User, int(payload["sub"]))
        if user and user.status == UserStatus.ACTIVE:
            return user
    except Exception:
        pass
    return None


def require_role(*allowed: UserRole):
    """生成一个 dependency,要求当前用户角色在 allowed 集合内。"""

    async def _dep(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="insufficient_role")
        return user

    return _dep


require_admin = require_role(UserRole.ADMIN)
require_merchant = require_role(UserRole.MERCHANT, UserRole.ADMIN)
