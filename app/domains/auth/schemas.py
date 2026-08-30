"""auth 领域请求/响应模型。

UserOut 只返回 id/username/role/created_at——绝不含 password_hash。
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserRegister(BaseModel):
    # best-practices: Excessively use Pydantic——入参校验交给字段约束
    username: str = Field(min_length=3, max_length=50, pattern="^[A-Za-z0-9_]+$")
    # bcrypt 只处理前 72 字节，超长密码会被静默截断，所以入参层就限死
    password: str = Field(min_length=8, max_length=72)


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # 允许从 ORM 对象直接构造

    id: int
    username: str
    role: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
