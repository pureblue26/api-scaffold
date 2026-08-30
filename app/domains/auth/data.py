"""auth 领域数据访问：查/改统一收拢，service 不直接接触 SQLAlchemy 查询。

为什么存在：
- 复用：auth 领域以后加新功能，直接调这里的接口，不手写 session 查询
- 规则集中：用户名唯一性（业务规则）只写在这里
- 写路径统一收尾：提交/刷新/唯一冲突兜底，防漏 refresh、忘 rollback
"""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.auth.exceptions import DuplicateUsernameError
from app.domains.auth.models import User


# ---------------- 查 ----------------

async def get_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def get_by_username(session: AsyncSession, username: str) -> User | None:
    return await session.scalar(select(User).where(User.username == username))


async def is_username_taken(
    session: AsyncSession, username: str, exclude_user_id: int | None = None
) -> bool:
    """用户名唯一性检查（业务规则）：注册传 None，改用户名传当前用户 id 排除自己。"""
    stmt = select(User.id).where(User.username == username)
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    return await session.scalar(stmt) is not None


async def list_all(session: AsyncSession) -> list[User]:
    result = await session.scalars(select(User).order_by(User.id))
    return list(result)


# ---------------- 改 ----------------

async def save(session: AsyncSession, user: User) -> User:
    """所有写操作的统一收尾：提交 + 刷新 + 唯一冲突兜底。

    防漏 refresh（返回过期对象）、忘 rollback（污染会话）；唯一索引冲突统一 409。
    """
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise DuplicateUsernameError()
    await session.refresh(user)
    return user
