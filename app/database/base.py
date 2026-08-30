"""数据库引擎与会话。

脚手架阶段还没有业务表；接入第一个模型后：
1. 在 models/ 里定义模型（继承 BaseModel）
2. 运行 uv run alembic revision --autogenerate -m "init" && uv run alembic upgrade head
3. 应用启动时可在此处加"表存在性检查"（参考 library_api 的 init_db）
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.DATABASE_URL, echo=settings.DATABASE_ECHO)
SessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：每个请求一个会话，用完自动关闭。"""
    async with SessionFactory() as session:
        yield session
