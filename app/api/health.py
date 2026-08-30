"""健康检查：liveness（进程活着）与 DB 连通性。"""
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
