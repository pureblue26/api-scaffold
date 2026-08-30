"""健康检查领域：liveness 与 DB 连通性。

这是领域结构的示范：业务领域在 app/domains/ 下自包含，
按需创建 router / schemas / models / dependencies / service / exceptions。
健康检查只需 router.py 一个文件。
"""
from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    settings = get_settings()
    return {"status": "ok", "environment": settings.ENVIRONMENT.value}


@router.get("/health/db")
async def health_db() -> dict:
    """用配置里的 DATABASE_URL 实际连一次数据库。

    数据库没启动时返回明确的错误信息，而不是应用静默挂掉。
    """
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as exc:  # noqa: BLE001 健康检查需要捕获一切失败并返回明确错误
        return {"status": "error", "database": str(exc)[:200]}
    finally:
        await engine.dispose()
