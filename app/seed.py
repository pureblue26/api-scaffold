"""初始化脚本：创建第一个管理员账号。

用法（项目根目录，先确保数据库在跑）：
    uv run python -m app.seed --password <密码>            # 用户名默认 admin
    uv run python -m app.seed --username boss --password xxx
    $env:ADMIN_PASSWORD='xxx'; uv run python -m app.seed    # 或读环境变量

幂等：用户名已存在则跳过，不覆盖密码。
切换环境：$env:ENVIRONMENT='test'; uv run python -m app.seed --password xxx
"""
import argparse
import asyncio
import os

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import SessionFactory
from app.domains.auth import data
from app.domains.auth.models import User
from app.domains.auth.security import hash_password


async def create_admin(session: AsyncSession, username: str, password: str) -> User | None:
    """创建管理员（幂等：已存在返回 None，不覆盖）。

    复用 auth 领域的数据层（get_by_username/save）和哈希逻辑——
    脚本是"入口"，业务逻辑住在领域里，不重复造轮子。
    """
    if len(password) < 8:
        raise ValueError("密码至少 8 位（与注册规则一致）")
    if await data.get_by_username(session, username):
        return None

    user = User(username=username, password_hash=hash_password(password), role="admin")
    session.add(user)
    return await data.save(session, user)


async def main() -> None:
    parser = argparse.ArgumentParser(description="初始化管理员账号")
    parser.add_argument("--username", default=os.getenv("ADMIN_USERNAME", "admin"))
    parser.add_argument("--password", default=os.getenv("ADMIN_PASSWORD"))
    args = parser.parse_args()

    if not args.password:
        parser.error("必须提供密码：--password <密码> 或环境变量 ADMIN_PASSWORD（不设默认密码）")

    async with SessionFactory() as session:
        user = await create_admin(session, args.username, args.password)

    if user:
        print(f"✅ 管理员 {args.username} 创建成功（role=admin）")
    else:
        print(f"ℹ️  用户名 {args.username} 已存在，跳过（如需重置密码请手动处理）")


if __name__ == "__main__":
    asyncio.run(main())
