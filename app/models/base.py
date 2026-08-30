"""ORM 模型基类：业务模型继承它，Alembic 以它的 metadata 为基准。"""
from sqlalchemy.orm import DeclarativeBase


class BaseModel(DeclarativeBase):
    pass
