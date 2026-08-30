"""API 路由聚合：新增业务模块时 include_router 进来即可。"""
from fastapi import APIRouter

from app.api import health

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
