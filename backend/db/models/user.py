"""用户域 ORM —— 一张 users 表承载 user/merchant/admin 三种角色,加 status 状态。

设计取舍:
- 用 role 字段而非多表继承,简化关联和迁移
- 商家特有字段(店铺名、营业执照号)作为可空列,role=merchant 时填写
- password_hash 用 bcrypt,plaintext 密码永远不进入数据库或日志
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, DateTime, Enum as SAEnum, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.session import Base


class UserRole(str, Enum):
    """用户角色 —— 与权限装饰器配合使用。"""

    USER = "user"  # 普通买家
    MERCHANT = "merchant"  # 商家(可上传商品,需审核)
    ADMIN = "admin"  # 平台管理员


class UserStatus(str, Enum):
    """账号状态 —— banned 后所有受保护接口拒绝。"""

    ACTIVE = "active"
    BANNED = "banned"


class User(Base):
    """用户主表 —— 买家/商家/管理员共用,role 区分。

    登录方式三选一(或组合):
    - 用户名 + 密码
    - 邮箱 + 密码
    - 手机号 + 验证码(无密码也允许,纯手机号注册的 password_hash 可为空)
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 三种登录标识至少一个非空;username 现在变成可空,首次手机号注册时由后端自动生成
    username: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(
        String(20), unique=True, index=True, comment="E.164 或 11 位裸号都行,统一规范化后存储"
    )
    # 纯手机号注册的用户 password_hash 可空(后续可在"设置密码"接口补)
    password_hash: Mapped[str | None] = mapped_column(String(128))

    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, native_enum=False, length=16), default=UserRole.USER, nullable=False
    )
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, native_enum=False, length=16),
        default=UserStatus.ACTIVE,
        nullable=False,
    )

    # 商家专属(role=merchant 时填),普通用户为 NULL
    shop_name: Mapped[str | None] = mapped_column(String(128))
    business_license: Mapped[str | None] = mapped_column(String(64), comment="营业执照号")
    contact_phone: Mapped[str | None] = mapped_column(String(32))

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
