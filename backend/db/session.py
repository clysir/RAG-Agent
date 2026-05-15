"""SQLAlchemy 2.0 异步会话工厂 —— 业务代码通过 FastAPI 依赖注入拿 session。

echo 由 settings.sql_echo 控制(dev=True / op=False),不要在这里硬编码。
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings

# dev 模式自动打印 SQL,op 模式静默
engine = create_async_engine(
    settings.mysql.async_dsn,
    echo=settings.sql_echo,
    pool_size=10,
    pool_recycle=3600,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类 —— Alembic autogenerate 会扫描这个基类。"""


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖项 —— session: AsyncSession = Depends(get_session)。"""
    async with SessionLocal() as session:
        yield session
