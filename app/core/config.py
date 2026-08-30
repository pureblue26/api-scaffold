"""环境配置：环境变量 > .env.<ENVIRONMENT> 文件 > 代码默认值。

生产环境做 fail-fast 校验：密钥缺失/弱密码/DEBUG=True 一律拒绝启动。
"""
import os
from enum import Enum
from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import env_file


class Environment(str, Enum):
    """运行环境枚举：杜绝拼写错误。"""

    DEV = "dev"
    TEST = "test"
    PROD = "prod"


class Settings(BaseSettings):
    """应用配置模型。字段声明即校验，类型错误启动即报错。"""

    model_config = SettingsConfigDict(
        env_file=env_file(os.getenv("ENVIRONMENT", Environment.DEV.value)),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------------- 环境 ----------------
    ENVIRONMENT: Environment = Environment.DEV

    # ---------------- 服务器 ----------------
    DEBUG: bool = False  # 安全默认值：默认关调试，由 .env.dev 显式开启
    VERSION: str = "0.1.0"
    SERVER_HOST: str = "127.0.0.1"
    SERVER_PORT: int = 8000
    # 密钥：本地用占位值；生产环境由 fail-fast 校验强制注入真实密钥
    SECRET_KEY: str = "dev-only-insecure-key"

    # ---------------- 数据库 ----------------
    # 拆成原始字段，由 DATABASE_URL property 拼装（密码特殊字符自动 URL 转义）
    DATABASE_TYPE: Literal["postgres"] = "postgres"
    DATABASE_HOST: str = "127.0.0.1"
    DATABASE_PORT: int = 5432
    DATABASE_USER: str = "postgres"
    DATABASE_PASSWORD: str = "postgres"
    DATABASE_NAME: str = "scaffold_dev"
    DATABASE_ECHO: bool = False

    # ---------------- Redis（全局基础设施） ----------------
    REDIS_URL: str = "redis://127.0.0.1:6380/0"

    @property
    def DATABASE_URL(self) -> str:
        """SQLAlchemy 异步连接串（密码含 @ : / 等特殊字符也能正确拼装）。"""
        return (
            f"postgresql+asyncpg://{self.DATABASE_USER}:{quote_plus(self.DATABASE_PASSWORD)}"
            f"@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"
        )

    @model_validator(mode="after")
    def _fail_fast_on_prod(self) -> "Settings":
        """生产环境 fail-fast：宁可启动失败，绝不带默认值上线。"""
        if self.ENVIRONMENT != Environment.PROD:
            return self

        if len(self.SECRET_KEY) < 32 or self.SECRET_KEY.startswith(("dev-", "test-", "prod-")):
            raise ValueError(
                "生产环境必须通过环境变量注入 SECRET_KEY（32 位以上随机串），禁止使用默认值"
            )
        if not self.DATABASE_PASSWORD or self.DATABASE_PASSWORD in ("postgres", "admin123"):
            raise ValueError("生产环境必须通过环境变量注入 DATABASE_PASSWORD，禁止使用默认密码")
        if self.DEBUG:
            raise ValueError("生产环境禁止 DEBUG=True")
        if not self.REDIS_URL or "127.0.0.1" in self.REDIS_URL:
            raise ValueError("生产环境必须注入 REDIS_URL，禁止使用本地默认值")
        return self


@lru_cache
def get_settings() -> Settings:
    """获取配置（进程内只解析一次）。"""
    return Settings()
