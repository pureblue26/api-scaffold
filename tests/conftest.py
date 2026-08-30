"""pytest 共享配置。

关键：测试用独立引擎（NullPool，每次新连接），
避免 TestClient 与全局引擎连接池的事件循环冲突。
"""
import os

# 强制测试使用 test 环境（必须在 import app 之前设置）
os.environ["ENVIRONMENT"] = "test"

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.database.base import get_session
from app.main import app


@pytest.fixture
def client():
    """每个测试：独立测试引擎 + 会话覆盖，返回 FastAPI TestClient。"""
    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    TestSession = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with TestSession() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    from fastapi.testclient import TestClient

    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        import asyncio

        asyncio.run(engine.dispose())
