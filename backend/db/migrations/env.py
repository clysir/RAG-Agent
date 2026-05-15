"""Alembic 异步迁移环境配置 —— 接入项目 settings + ORM Base。

要点:
- sqlalchemy.url 不写在 alembic.ini 里,运行时从 settings.mysql.async_dsn 注入,
  与业务代码共用同一个配置入口(CLAUDE.md 规则 #2)。
- target_metadata 指向 db.Base.metadata,并在文件顶部 import db.models 触发模型注册,
  这样 autogenerate 才能识别全部表(User / Product / Session / Message / ProductSubmission)。
- 走异步引擎,与运行时栈一致,避免 sync/async 驱动差异导致的迁移误差。
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# 把项目配置 + ORM Base 引入,顺手 import db.models 触发全部模型注册
from config import settings
from db import Base
import db.models  # noqa: F401  仅为副作用注册 User/Product/Session/Message/ProductSubmission

# Alembic Config 对象,提供 .ini 文件内的值
config = context.config

# 运行时把 DSN 注入(覆盖 .ini 里的占位),避免硬编码
config.set_main_option("sqlalchemy.url", settings.mysql.async_dsn)

# 配置 Python 日志
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# autogenerate 用的元数据
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式 —— 只输出 SQL 不连库,用于生成审阅用的 SQL 文件。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,  # 检测列类型变化
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """在线模式 —— 走异步引擎跑迁移。"""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """在线模式入口。"""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
