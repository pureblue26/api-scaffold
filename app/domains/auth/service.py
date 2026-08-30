"""auth 业务逻辑：规则住在这里，router 只做编排。"""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.auth.exceptions import DuplicateUsernameError, InvalidCredentialsError
from app.domains.auth.models import User
from app.domains.auth.security import hash_password, verify_password


async def register(session: AsyncSession, username: str, password: str) -> User:
    """注册：先查重，再插入；唯一约束兜底并发竞态。

    两个请求同时注册同一用户名时，两边的"查重"都会通过，
    最终靠数据库 unique 约束兜底：第二次插入抛 IntegrityError → 409。
    """
    existing = await session.scalar(select(User).where(User.username == username))
    if existing:
        raise DuplicateUsernameError()

    user = User(username=username, password_hash=hash_password(password))
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise DuplicateUsernameError()
    await session.refresh(user)
    return user


async def authenticate(session: AsyncSession, username: str, password: str) -> User:
    """登录：查用户 + 校验密码。

    用户名不存在 和 密码错误 返回同一个错误——防止攻击者探测哪些用户名已注册（用户枚举）。
    """
    user = await session.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError()
    return user


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def list_users(session: AsyncSession) -> list[User]:
    result = await session.scalars(select(User).order_by(User.id))
    return list(result)
