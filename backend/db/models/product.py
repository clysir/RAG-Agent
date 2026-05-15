"""商品 ORM —— 业务结构化字段存 MySQL,向量存 Milvus(通过 product_id 关联)。

merchant_id:
- 商家自上传商品 -> 关联到 User.id(role=merchant)
- 公开数据集灌入的商品 -> NULL,视作"平台直营"
"""

from datetime import datetime

from sqlalchemy import (
    DECIMAL,
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.session import Base


class Product(Base):
    """商品主表 —— 标题、类目、价格、参数、图片、库存等结构化数据。"""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # NULL 表示平台/数据集来源,非空表示商家上传
    merchant_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True
    )

    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    brand: Mapped[str | None] = mapped_column(String(128))
    price: Mapped[float] = mapped_column(DECIMAL(10, 2), nullable=False, index=True)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[str | None] = mapped_column(Text, comment="JSON 字符串,商品扩展参数")
    # 主图存储 key(对象存储里);老数据可能直接是 URL,展示时 Storage.presign 兼容处理
    image_object_key: Mapped[str | None] = mapped_column(String(512))

    rating: Mapped[float | None] = mapped_column(DECIMAL(3, 2))
    review_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
