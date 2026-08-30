"""pytest 共享配置。

关键：测试用独立引擎（NullPool，每次新连接），
避免 TestClient 与全局引擎连接池的事件循环冲突。
"""
import asyncio
import os

# 强制测试使用 test 环境（必须在 import app 之前设置）
os.environ["ENVIRONMENT"] = "test"

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.redis import close_redis, get_redis
from app.database.base import get_session
from app.main import app
from app.models.base import BaseModel


@pytest.fixture(scope="session", autouse=True)
def redis_ready():
    """Redis 由 get_redis 按事件循环自动创建；会话结束统一关闭。"""
    yield
    asyncio.run(close_redis())


@pytest.fixture
def client():
    """每个测试：独立测试引擎 + 建表清空 + 会话覆盖，返回 FastAPI TestClient。"""
    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    TestSession = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with TestSession() as session:
            yield session

    async def setup():
        # 建表（幂等）+ 清空，保证测试隔离
        async with engine.begin() as conn:
            await conn.run_sync(BaseModel.metadata.create_all)
        async with TestSession() as session:
            await session.execute(text("TRUNCATE TABLE order_items, orders, products, users RESTART IDENTITY CASCADE"))
            await session.commit()

    asyncio.run(setup())

    async def flush_redis():
        await (await get_redis()).flushdb()  # 每个测试前清空缓存/黑名单/限流计数

    asyncio.run(flush_redis())
    app.state.test_session_factory = TestSession
    app.dependency_overrides[get_session] = override_session
    from fastapi.testclient import TestClient

    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        app.state.test_session_factory = None
        asyncio.run(engine.dispose())


def make_admin(client, user_id: int) -> None:
    """测试辅助：把用户提升为管理员（模拟 DBA 授权）。

    真实项目里"第一个管理员怎么产生"是种子脚本的问题，测试里直接改库模拟。
    """
    factory = client.app.state.test_session_factory

    async def promote():
        async with factory() as session:
            await session.execute(
                text("UPDATE users SET role = 'admin' WHERE id = :uid"), {"uid": user_id}
            )
            await session.commit()

    asyncio.run(promote())