"""会话与消息 ORM —— 多轮对话持久化,长期记忆来源。

短期记忆(几轮内)放 Redis,这里存的是完整历史用于回放和分析。
user_id 是 FK,匿名访客暂走 NULL(后续可强制登录)。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.session import Base


class Session(Base):
    """对话会话 —— 一个用户的一段连续对话。"""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # UUID
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True, comment="未登录访客为 NULL"
    )
    title: Mapped[str | None] = mapped_column(String(256))

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(back_populates="session")


class Message(Base):
    """单条消息 —— 用户输入或 Agent 输出。"""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user/assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 用户上传图片的 storage object key,展示通过 presign
    image_object_key: Mapped[str | None] = mapped_column(String(512))
    # Agent 关键中间状态的 JSON 快照,便于复盘和评估
    trace_data: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    session: Mapped["Session"] = relationship(back_populates="messages")
