"""认证路由 —— 注册、登录、当前用户、手机号验证码登录。

设计:
- 登录用 OAuth2PasswordRequestForm,与 OpenAPI 的 Authorize 按钮兼容
- 注册返回 user 信息,不自动登录(让前端显式调登录)
- 商家注册走单独接口,补充店铺字段;status 仍是 active(简化版,生产可加入驻审核)
- 手机号验证码登录是国内 ToC 主流方式,首次登录自动注册
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.core.sms_service import (
    SmsCodeInvalid,
    SmsDailyExceeded,
    SmsError,
    SmsRateLimited,
    send_verification_code,
    verify_code,
)
from config import settings
from db import User, UserRole, UserStatus, get_session
from schemas import (
    CurrentUser,
    Envelope,
    RegisterMerchantRequest,
    RegisterRequest,
    SmsLoginRequest,
    SmsSendRequest,
    SmsSendResponse,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


async def _check_username_email_free(
    session: AsyncSession, username: str, email: str | None
) -> None:
    """检查用户名/邮箱是否已被占用 —— 占用了抛 409。"""
    conds = [User.username == username]
    if email:
        conds.append(User.email == email)
    # or_() 不允许传列表 故需要*解包
    exists = await session.scalar(select(User).where(or_(*conds)))
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="username_or_email_taken")


@router.post("/register", response_model=Envelope[CurrentUser])
async def register(
    payload: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[CurrentUser]:
    """普通用户注册。 用户名 + 邮箱 + 密码"""
    await _check_username_email_free(session, payload.username, payload.email)

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    return Envelope[CurrentUser](
        data=CurrentUser(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role.value,
            status=user.status.value,
        )
    )


@router.post("/register/merchant", response_model=Envelope[CurrentUser])
async def register_merchant(
    payload: RegisterMerchantRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[CurrentUser]:
    """商家注册 —— 简化:不做入驻审核,直接 active,后续上传商品要走审核。"""
    await _check_username_email_free(session, payload.username, payload.email)

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=UserRole.MERCHANT,
        status=UserStatus.ACTIVE,
        shop_name=payload.shop_name,
        business_license=payload.business_license,
        contact_phone=payload.contact_phone,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    return Envelope[CurrentUser](
        data=CurrentUser(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role.value,
            status=user.status.value,
            shop_name=user.shop_name,
        )
    )


@router.post("/login", response_model=Envelope[TokenResponse])
async def login(
    # OAuth2PasswordRequestForm 用 form 字段 username + password,与 Swagger Authorize 兼容
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[TokenResponse]:
    """登录 —— 返回 JWT access token。"""
    user = await session.scalar(select(User).where(User.username == form.username))
    # 用户不存在和密码错都返同一种错,避免泄露用户存在性
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")
    if user.status == UserStatus.BANNED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="user_banned")

    token = create_access_token(user_id=user.id, role=user.role.value)
    # 顺手更新 last_login_at
    user.last_login_at = datetime.now(timezone.utc)
    await session.commit()

    return Envelope[TokenResponse](
        data=TokenResponse(
            access_token=token,
            expires_in=settings.auth.jwt_access_ttl_minutes * 60,
        )
    )


@router.get("/me", response_model=Envelope[CurrentUser])
async def me(user: Annotated[User, Depends(get_current_user)]) -> Envelope[CurrentUser]:
    """获取当前登录用户信息。"""
    return Envelope[CurrentUser](
        data=CurrentUser(
            id=user.id,
            username=user.username,
            email=user.email,
            phone=user.phone,
            role=user.role.value,
            status=user.status.value,
            shop_name=user.shop_name,
        )
    )


# ============ 手机号验证码登录 ============


@router.post("/sms/send", response_model=Envelope[SmsSendResponse])
async def send_sms_code(payload: SmsSendRequest) -> Envelope[SmsSendResponse]:
    """发送短信验证码 —— 默认 mock provider 把验证码打到日志。

    频率限制(默认值,可在 .env 调):
    - 同一手机号两次发送间隔 ≥ 60 秒
    - 单日上限 10 次
    """
    try:
        result = await send_verification_code(payload.phone)
    except SmsRateLimited as e:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))
    except SmsDailyExceeded as e:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))
    except SmsError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(e))

    return Envelope[SmsSendResponse](
        data=SmsSendResponse(
            sent=result["sent"],
            ttl=result["ttl"],
            code=result.get("code"),
        )
    )


@router.post("/sms/login", response_model=Envelope[TokenResponse])
async def sms_login(
    payload: SmsLoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[TokenResponse]:
    """手机号 + 验证码登录 —— 用户不存在则自动注册。

    流程:
    1. 校验验证码,通过后立即销毁(防重放)
    2. 查 phone 是否已注册;没注册就建一个 status=active 的普通用户
    3. 已注册但 banned 的拒绝
    4. 签 JWT 返回
    """
    # 1. 校验验证码
    try:
        await verify_code(payload.phone, payload.code)
    except SmsCodeInvalid as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))

    # 2. 查/建用户
    user = await session.scalar(select(User).where(User.phone == payload.phone))
    if user is None:
        # 手机号首次登录 = 注册;username 留空,password_hash 留空(用户后续可在设置里补)
        user = User(
            phone=payload.phone,
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
        )
        session.add(user)
        await session.flush()

    # 3. banned 拒绝
    if user.status == UserStatus.BANNED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="user_banned")

    user.last_login_at = datetime.now(timezone.utc)
    await session.commit()

    # 4. 签 token
    token = create_access_token(user_id=user.id, role=user.role.value)
    return Envelope[TokenResponse](
        data=TokenResponse(
            access_token=token,
            expires_in=settings.auth.jwt_access_ttl_minutes * 60,
        )
    )
