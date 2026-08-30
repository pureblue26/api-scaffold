"""auth 业务逻辑：只关心"做什么"，查询/存储在 data.py，token 失效机制在 Redis。"""
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.domains.auth import data
from app.domains.auth.exceptions import DuplicateUsernameError, InvalidCredentialsError
from app.domains.auth.models import User
from app.domains.auth.security import hash_password, verify_password

# Redis 键模板
USER_VER_KEY = "auth:user:{user_id}:ver"   # 用户 token 版本号（改密 +1）
BLACKLIST_KEY = "jwt:blacklist:{jti}"      # 登出的 token（TTL=剩余有效期）


async def get_user_epoch(user_id: int) -> int:
    """当前 token 版本号：登录时写进 token；改密时 +1 让旧 token 全部失效。"""
    val = await (await get_redis()).get(USER_VER_KEY.format(user_id=user_id))
    return int(val) if val else 1


async def is_token_revoked(payload: dict) -> bool:
    """jti 黑名单检查（登出后立即失效）。"""
    jti = payload.get("jti")
    if not jti:
        return False  # 无 jti 的旧格式 token：无法黑名单，放行
    return await (await get_redis()).exists(BLACKLIST_KEY.format(jti=jti)) == 1


async def verify_token_valid(payload: dict, user_id: int) -> bool:
    """双检查：黑名单 + 版本号。任一不过即失效。"""
    if await is_token_revoked(payload):
        return False
    return payload.get("ver", 1) == await get_user_epoch(user_id)


async def logout(user_id: int, payload: dict) -> None:
    """登出：把当前 token 加入黑名单。

    TTL = token 剩余有效期——token 过期后黑名单自动消失，无需手动清理。
    """
    exp = payload["exp"]
    remaining = max(0, exp - int(datetime.now(UTC).timestamp()))
    await (await get_redis()).set(BLACKLIST_KEY.format(jti=payload["jti"]), "1", ex=remaining)


async def register(session: AsyncSession, username: str, password: str) -> User:
    """注册：查重 → 哈希 → 建用户。用户名重复抛异常。"""
    if await data.is_username_taken(session, username):
        raise DuplicateUsernameError()

    user = User(username=username, password_hash=hash_password(password))
    session.add(user)
    return await data.save(session, user)


async def authenticate(session: AsyncSession, username: str, password: str) -> User:
    """登录：查用户 + 校验密码。用户不存在和密码错误返回同一错误（防用户枚举）。"""
    user = await data.get_by_username(session, username)
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError()
    return user


async def update_username(session: AsyncSession, user: User, new_username: str) -> User:
    """改用户名：排除自己查重（并发兜底仍由 data.save 的唯一索引处理）。"""
    if new_username == user.username:
        return user  # 幂等：没变化直接返回
    if await data.is_username_taken(session, new_username, exclude_user_id=user.id):
        raise DuplicateUsernameError()

    user.username = new_username
    return await data.save(session, user)


async def update_password(
    session: AsyncSession, user: User, old_password: str, new_password: str
) -> User:
    """改密码：先验证旧密码，再哈希新密码。"""
    if not verify_password(old_password, user.password_hash):
        raise InvalidCredentialsError("旧密码不正确")

    user.password_hash = hash_password(new_password)
    saved = await data.save(session, user)
    # 改密后：版本号 +1，该用户所有已签发 token 立即失效（token_version 模式）。
    # 注意：不能用 INCR——INCR 对不存在的键从 1 开始，而旧 token 的 ver 也是 1，
    # 必须显式"当前值 + 1"（并发下版本号只会更大，语义依然正确）。
    ver = await get_user_epoch(user.id)
    await (await get_redis()).set(USER_VER_KEY.format(user_id=user.id), ver + 1)
    return saved


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await data.get_by_id(session, user_id)


async def list_users(session: AsyncSession) -> list[User]:
    return await data.list_all(session)