"""auth 领域接口：注册 / 登录 / 当前用户 / 用户列表。"""
from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import rate_limit
from app.database.base import get_session
from app.domains.auth import service
from app.domains.auth.dependencies import (
    bearer_scheme,
    get_current_user,
    require_admin,
)
from app.domains.auth.models import User
from app.domains.auth.schemas import (
    PasswordUpdate,
    TokenOut,
    UserLogin,
    UsernameUpdate,
    UserOut,
    UserRegister,
)
from app.domains.auth.security import create_access_token, decode_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
async def register(data: UserRegister, session: AsyncSession = Depends(get_session)) -> UserOut:
    """注册。201 返回新用户信息（不含密码哈希）。"""
    user = await service.register(session, data.username, data.password)
    return UserOut.model_validate(user)


@router.post("/login", response_model=TokenOut, dependencies=[Depends(rate_limit(5, 60))])
async def login(data: UserLogin, session: AsyncSession = Depends(get_session)) -> TokenOut:
    """登录：用户名密码换 JWT。"""
    user = await service.authenticate(session, data.username, data.password)
    ver = await service.get_user_epoch(user.id)
    return TokenOut(access_token=create_access_token(user.id, ver=ver))


@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    current_user: User = Depends(get_current_user),
) -> dict:
    """登出：当前 token 立即失效（黑名单 TTL = 剩余有效期）。"""
    payload = decode_access_token(credentials.credentials)
    await service.logout(current_user.id, payload)
    return {"message": "已登出"}


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    """当前登录用户信息（演示认证依赖的用法）。"""
    return UserOut.model_validate(current_user)


@router.patch("/me/username", response_model=UserOut)
async def update_username(
    data: UsernameUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    """修改当前用户用户名（重名返回 409）。"""
    user = await service.update_username(session, current_user, data.new_username)
    return UserOut.model_validate(user)


@router.patch("/me/password", response_model=UserOut)
async def update_password(
    data: PasswordUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    """修改当前用户密码（需验证旧密码）。"""
    user = await service.update_password(
        session, current_user, data.old_password, data.new_password
    )
    return UserOut.model_validate(user)


@router.get("/users", response_model=list[UserOut])
async def users(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> list[UserOut]:
    """列出所有用户（仅管理员，演示角色校验）。"""
    users = await service.list_users(session)
    return [UserOut.model_validate(u) for u in users]
