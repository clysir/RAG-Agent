"""认证相关 schema —— 注册、登录、当前用户信息。"""

import re

from pydantic import EmailStr, Field, field_validator

from schemas.common import APIModel


# 中国大陆手机号校验:1 开头 11 位数字。国际场景可放宽到 E.164 +xxxxx
_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")


def _normalize_phone(v: str) -> str:
    """统一手机号格式 —— 去空格、去 +86 前缀。"""
    v = v.strip().replace(" ", "").replace("-", "")
    if v.startswith("+86"):
        v = v[3:]
    if not _PHONE_RE.match(v):
        raise ValueError("invalid_phone_number")
    return v


class RegisterRequest(APIModel):
    """注册入参 —— 默认 role=user;merchant 注册走单独接口需带营业执照等字段。"""

    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_]+$")
    email: EmailStr | None = None
    password: str = Field(..., min_length=8, max_length=128)


class RegisterMerchantRequest(RegisterRequest):
    """商家注册入参 —— 补充店铺信息,role 自动置为 merchant,status 仍 active(简化版不审核入驻)。"""

    shop_name: str = Field(..., min_length=1, max_length=128)
    business_license: str = Field(..., min_length=1, max_length=64)
    contact_phone: str | None = Field(None, max_length=32)


class LoginRequest(APIModel):
    """登录入参 —— 用户名 + 密码。"""

    username: str
    password: str


class TokenResponse(APIModel):
    """登录成功返回 access token。"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="秒数")


class CurrentUser(APIModel):
    """GET /auth/me 返回 —— 不暴露 password_hash。"""

    id: int
    username: str | None = None
    email: str | None = None
    phone: str | None = None
    role: str
    status: str
    shop_name: str | None = None


# ============ 手机号验证码登录 ============


class SmsSendRequest(APIModel):
    """发送验证码 —— POST /auth/sms/send。"""

    phone: str

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, v: str) -> str:
        return _normalize_phone(v)


class SmsSendResponse(APIModel):
    """发送验证码响应 —— mock + dev 模式会带 code 方便联调。"""

    sent: bool = True
    ttl: int = Field(..., description="验证码有效期(秒)")
    code: str | None = Field(None, description="仅 mock+dev 模式回传,生产为 None")


class SmsLoginRequest(APIModel):
    """手机号 + 验证码登录/注册。

    用户不存在时自动注册(以手机号为唯一标识),已存在直接签 token。
    这是国内 ToC 产品最主流的免密登录方式。
    """

    phone: str
    code: str = Field(..., min_length=4, max_length=8)

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, v: str) -> str:
        return _normalize_phone(v)
