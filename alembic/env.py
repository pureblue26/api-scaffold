"""Alembic 迁移环境：数据库连接串从应用配置读取（config.py 的 DATABASE_URL）。"""
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import get_settings

# 注册所有领域模型：导入即把表注册进 BaseModel.metadata（autogenerate 才能发现）
from app.domains.auth import models  # noqa: F401
from app.models.base import BaseModel

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 关键：用应用配置覆盖 alembic.ini 里的 sqlalchemy.url（.env.* 由配置层加载）
config.set_main_option("sqlalchemy.url", get_settings().DATABASE_URL)

target_metadata = BaseModel.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
