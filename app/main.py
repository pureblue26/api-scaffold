"""应用入口：装配配置、异常处理、路由。"""
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("scaffold")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("应用启动 | 环境=%s | DEBUG=%s", settings.ENVIRONMENT.value, settings.DEBUG)
    logger.info("数据库: %s", settings.DATABASE_URL)
    yield
    logger.info("应用关闭")


settings = get_settings()
app = FastAPI(title="API Scaffold", version=settings.VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发期允许所有来源；生产收紧为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router)


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
