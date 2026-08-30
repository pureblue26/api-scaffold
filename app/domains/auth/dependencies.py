"""auth 领域依赖：解析当前用户、管理员校验。

FastAPI 会在单个请求内缓存 Depends 结果——同一个请求里多处依赖
get_current_user 只会真正执行一次（best-practices: Dependency calls are cached）。
"""
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.database.base import get_session
from app.domains.auth import service
from app.domains.auth.exceptions import InvalidTokenError
from app.domains.auth.models import User
from app.domains.auth.security import decode_access_token

# auto_error=False：拿不到凭证时自己抛 401（错误信息可控），而不是框架默认 403
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    """从 Authorization: Bearer <token> 解析出当前用户。"""
    if credentials is None:
        raise UnauthorizedError("缺少认证凭证")
    try:
        payload = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise UnauthorizedError("无效或过期的令牌")

    user = await service.get_user_by_id(session, int(payload["sub"]))
    if user is None:
        raise UnauthorizedError("用户不存在")
    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """要求当前用户是管理员，否则 403。"""
    if current_user.role != "admin":
        raise ForbiddenError("需要管理员权限")
    return current_user
