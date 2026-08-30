"""auth 领域配置：与全局配置解耦（best-practices: Decouple Pydantic BaseSettings）。

JWT 相关的密钥/算法/过期时间属于 auth 领域，不塞进全局 Settings。
"""
import os

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import Environment
from app.core.paths import env_file


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=env_file(os.getenv("ENVIRONMENT", "dev")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ENVIRONMENT: Environment = Environment.DEV
    JWT_SECRET: str = "dev-only-jwt-secret"
    JWT_ALG: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 30

    @model_validator(mode="after")
    def _fail_fast_on_prod(self) -> "AuthSettings":
        """生产环境：JWT 密钥同样禁止默认值（与全局 SECRET_KEY 同理）。"""
        if self.ENVIRONMENT == Environment.PROD and (
            len(self.JWT_SECRET) < 32 or self.JWT_SECRET.startswith("dev-")
        ):
            raise ValueError("生产环境必须通过环境变量注入 JWT_SECRET（32 位以上随机串）")
        return self


# 模块级单例：整个进程只解析一次
auth_settings = AuthSettings()
