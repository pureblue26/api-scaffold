"""auth 业务逻辑：只关心"做什么"，查询/存储细节在 data.py。"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.auth import data
from app.domains.auth.exceptions import DuplicateUsernameError, InvalidCredentialsError
from app.domains.auth.models import User
from app.domains.auth.security import hash_password, verify_password


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
    return await data.save(session, user)


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await data.get_by_id(session, user_id)


async def list_users(session: AsyncSession) -> list[User]:
    return await data.list_all(session)
