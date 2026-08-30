"""密码哈希与 JWT 签发/验证。

为什么换库：
- passlib 已停止维护，且与 bcrypt>=4.1 有已知兼容问题（旧项目被迫锁死 bcrypt==4.0.1）
- python-jose 同样长期不维护；PyJWT 是社区当前主流，API 更简单
"""
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.domains.auth.config import auth_settings
from app.domains.auth.exceptions import InvalidTokenError

# ---------------- 密码哈希 ----------------

def hash_password(password: str) -> str:
    """bcrypt 哈希。

    盐（salt）随机生成并内嵌在结果串里，所以不需要单独存盐列。
    bcrypt 只取前 72 字节输入——schemas 层已把密码限制在 72 字符内。
    """
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """校验密码。bcrypt.checkpw 内部是恒定时间比较，抗时序攻击。"""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ---------------- JWT ----------------

def create_access_token(user_id: int) -> str:
    """签发 JWT。

    payload 三个字段：
    - sub: 用户 id（字符串，JWT 标准规定 sub 必须是字符串）
    - exp: 过期时间（PyJWT 解码时自动校验，过期直接报错）
    - iat: 签发时间（审计用）
    """
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=auth_settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, auth_settings.JWT_SECRET, algorithm=auth_settings.JWT_ALG)


def decode_access_token(token: str) -> dict:
    """验签 + 检查过期，返回 payload。任何失败都归一到 InvalidTokenError。"""
    try:
        return jwt.decode(token, auth_settings.JWT_SECRET, algorithms=[auth_settings.JWT_ALG])
    except jwt.PyJWTError:
        raise InvalidTokenError()
