"""auth 领域接口：注册 / 登录 / 当前用户 / 用户列表。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import get_session
from app.domains.auth import service
from app.domains.auth.dependencies import get_current_user, require_admin
from app.domains.auth.models import User
from app.domains.auth.schemas import TokenOut, UserLogin, UserOut, UserRegister
from app.domains.auth.security import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
async def register(data: UserRegister, session: AsyncSession = Depends(get_session)) -> UserOut:
    """注册。201 返回新用户信息（不含密码哈希）。"""
    user = await service.register(session, data.username, data.password)
    return UserOut.model_validate(user)


@router.post("/login", response_model=TokenOut)
async def login(data: UserLogin, session: AsyncSession = Depends(get_session)) -> TokenOut:
    """登录：用户名密码换 JWT。"""
    user = await service.authenticate(session, data.username, data.password)
    return TokenOut(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    """当前登录用户信息（演示认证依赖的用法）。"""
    return UserOut.model_validate(current_user)


@router.get("/users", response_model=list[UserOut])
async def users(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> list[UserOut]:
    """列出所有用户（仅管理员，演示角色校验）。"""
    users = await service.list_users(session)
    return [UserOut.model_validate(u) for u in users]
