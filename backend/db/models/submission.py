"""商品提交记录 —— 商家上传走的中间态,审核通过后才进 products 主表。

工作流:
1. 商家 POST /merchant/products -> 创建 ProductSubmission(status=pending)
   同时把图片上传到对象存储,记录 image_object_key
2. 管理员 POST /admin/submissions/{id}/approve
   -> 创建 Product(merchant_id 关联) + 触发 Celery 入库 build_index_for_product
   -> ProductSubmission.status=approved
3. 管理员 POST /admin/submissions/{id}/reject
   -> 写 reject_reason,商家可见
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    DECIMAL,
    BigInteger,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.session import Base


class SubmissionStatus(str, Enum):
    PENDING = "pending"  # 待审核
    APPROVED = "approved"  # 已通过(已生成 Product)
    REJECTED = "rejected"  # 已驳回


class ProductSubmission(Base):
    """商家提交的商品草稿,等管理员审核。"""

    __tablename__ = "product_submissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    merchant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(128))
    price: Mapped[float] = mapped_column(DECIMAL(10, 2), nullable=False)
    stock: Mapped[int] = mapped_column(BigInteger, default=0)
    description: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[str | None] = mapped_column(Text, comment="JSON 字符串")

    # 对象存储里的图片 key,展示时通过 presign 拿临时 URL
    image_object_key: Mapped[str | None] = mapped_column(String(512))

    status: Mapped[SubmissionStatus] = mapped_column(
        SAEnum(SubmissionStatus, native_enum=False, length=16),
        default=SubmissionStatus.PENDING,
        nullable=False,
        index=True,
    )
    reviewer_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    reject_reason: Mapped[str | None] = mapped_column(String(512))
    approved_product_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("products.id"), comment="通过后生成的商品 ID"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
