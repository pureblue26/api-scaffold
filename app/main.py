"""应用入口：装配全局（配置/异常/数据库）与各领域路由。"""
import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.metrics import MetricsMiddleware
from app.core.redis import close_redis, init_redis
from app.core.request_id import RequestIdMiddleware
from app.domains.auth.router import router as auth_router
from app.domains.health.router import router as health_router
from app.domains.store.router import router as store_router
from app.domains.store.tasks import order_expiry_loop

setup_logging()  # JSON 结构化日志 + request_id 注入
logger = logging.getLogger("scaffold")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("应用启动 | 环境=%s | DEBUG=%s", settings.ENVIRONMENT.value, settings.DEBUG)
    logger.info("数据库: %s", settings.DATABASE_URL)
    await init_redis()
    logger.info("Redis: %s", settings.REDIS_URL)
    # 订单超时自动取消后台任务
    expiry_task = asyncio.create_task(order_expiry_loop())
    logger.info("订单超时清扫任务已启动（间隔 60s）")
    yield
    expiry_task.cancel()
    logger.info("应用关闭")
    await close_redis()


settings = get_settings()
app = FastAPI(title="API Scaffold", version=settings.VERSION, lifespan=lifespan)

app.add_middleware(RequestIdMiddleware)  # 请求 ID：日志/响应可关联
app.add_middleware(MetricsMiddleware)  # Prometheus 指标（RED）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发期允许所有来源；生产收紧为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

# 领域路由：每个领域一个 include_router（在 include 之前 import 该领域，
# 其 exceptions.py 会被自动注册）
app.include_router(auth_router, prefix="/api")
app.include_router(store_router, prefix="/api")
app.include_router(health_router, prefix="/api")


@app.get("/")
async def root() -> dict:
    return {
        "app": "api-scaffold",
        "environment": settings.ENVIRONMENT.value,
        "version": settings.VERSION,
        "docs": "/docs",
    }


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.SERVER_HOST, port=settings.SERVER_PORT)
