"""ORM 模型。接入业务模型后在这里统一导出，供 Alembic 发现。"""
from app.models.base import BaseModel

__all__ = ["BaseModel"]
