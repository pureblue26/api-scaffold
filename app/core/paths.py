"""路径与文件常量。"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env_file(environment: str) -> Path:
    """返回指定环境对应的 .env 文件路径，如 .env.dev / .env.prod。"""
    return BASE_DIR / f".env.{environment}"
