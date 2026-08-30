"""seed 脚本测试：管理员创建、幂等、哈希、真实可用。"""
import asyncio

from app.domains.auth import data
from app.seed import create_admin


def test_create_admin_success_and_idempotent(client):
    factory = client.app.state.test_session_factory

    async def run():
        async with factory() as session:
            user = await create_admin(session, "seedadmin", "password123")
            assert user is not None
            assert user.role == "admin"

            # 幂等：重复执行不报错、不覆盖
            assert await create_admin(session, "seedadmin", "password123") is None

            # 密码是哈希，不是明文
            db_user = await data.get_by_username(session, "seedadmin")
            assert db_user.password_hash != "password123"

    asyncio.run(run())


def test_create_admin_requires_strong_password(client):
    factory = client.app.state.test_session_factory

    async def run():
        async with factory() as session:
            try:
                await create_admin(session, "weak", "short")
            except ValueError:
                return
            raise AssertionError("弱密码应被拒绝")

    asyncio.run(run())


def test_seeded_admin_can_manage_products(client):
    """seed 出来的管理员，登录后真的能建商品（权限链路打通）。"""
    factory = client.app.state.test_session_factory

    async def run():
        async with factory() as session:
            await create_admin(session, "boss", "password123")

    asyncio.run(run())

    token = client.post(
        "/api/auth/login", json={"username": "boss", "password": "password123"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = client.post(
        "/api/products", json={"name": "种子商品", "price": 100, "stock": 5}, headers=headers
    )
    assert r.status_code == 201, r.text
