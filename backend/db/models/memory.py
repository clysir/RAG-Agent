"""用户长期记忆 —— 离散事实表,Mem0 风格的可单独 update/invalidate 结构。

设计要点:
1. 离散事实而非大段摘要 —— 单条可独立更新/失效,不像摘要更新就要重做
2. 双时态轻量版:valid_from / valid_to,valid_to NULL 表示当前有效
   - "刚才尺码是 M,现在改 L" -> 旧记录 valid_to=now(),新记录插入,而不是 UPDATE
3. user_id 严格隔离 —— 检索时强制过滤,Milvus 这边按 user_id 做 partition
4. last_used_at 用于 decay,180 天无读命中走 Celery beat 自动失效
5. vector_id 与 Milvus 主键一致,删除时双向同步

为何不放在 conversation.py:
- Message 是会话级事实记录(原始消息),UserMemory 是用户级提炼事实
- 两者生命周期、隔离粒度、检索路径都不同
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.session import Base


class FactType(str, Enum):
    """事实类型 —— 电商导购场景常见维度。

    抽取阶段 LLM 按这个枚举分类,检索时可按 type 过滤(如"找尺码偏好")。
    """

    PREFERENCE = "preference"  # 通用偏好:风格/颜色/材质
    SIZE = "size"  # 尺码 / 身材数据
    BRAND = "brand"  # 品牌偏好(喜欢/避雷)
    BUDGET = "budget"  # 预算区间
    ALLERGY = "allergy"  # 过敏 / 忌口 / 成分敏感
    ADDRESS = "address"  # 收货地址相关
    OCCASION = "occasion"  # 常见使用场合(通勤/健身)
    ORDER_HISTORY = "order_history"  # 历史订单关键事实
    RETURN_HISTORY = "return_history"  # 退货 / 售后事实
    OTHER = "other"  # 兜底


class UserMemory(Base):
    """用户级长期事实 —— 一条事实一行,失效用 valid_to 标记不删除。"""

    __tablename__ = "user_memories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    fact_type: Mapped[FactType] = mapped_column(
        SAEnum(FactType, native_enum=False, length=24),
        nullable=False,
        index=True,
    )
    # 自然语言事实文本,例如 "偏好极简风格的女装,不喜欢印花"
    fact_text: Mapped[str] = mapped_column(Text, nullable=False)

    # 抽取来源 —— 哪条 message 提炼出来的,便于排查/隐私撤回
    source_msg_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="SET NULL")
    )
    # 抽取器给的可信度,0-1
    confidence: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)

    # 双时态字段 —— Zep 风格的轻量版
    valid_from: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    # NULL = 当前有效;非空 = 失效时间(被新事实顶替或用户主动忘记)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, index=True)

    # decay 用:每次读命中后更新,180 天未读 Celery beat 失效
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Milvus 主键 —— 同步删除时用,生成规则 = sha256(user_id + fact_text + model + version)
    vector_id: Mapped[int | None] = mapped_column(BigInteger, index=True, unique=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # (user_id, valid_to) 联合索引 —— 检索"当前有效"和"按用户查"都是热路径
        Index("ix_user_memories_user_valid", "user_id", "valid_to"),
    )
