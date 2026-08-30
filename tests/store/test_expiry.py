"""订单超时测试：支付防线（过期不能支付）+ 清扫器（自动取消回补）。"""
import asyncio

from sqlalchemy import text

from app.domains.store import service
from tests.conftest import make_admin
from tests.store.test_store import _create_order, _create_product, _register


def _setup(client, stock=10):
    admin_id, admin_headers = _register(client, "admin")
    make_admin(client, admin_id)
    product = _create_product(client, admin_headers, stock=stock)
    _, user_headers = _register(client, "bob")
    return admin_headers, user_headers, product["id"]


def _expire_order(client, order_id):
    """把订单 created_at 拨到超时时限之前（模拟时间流逝 31 分钟）。"""
    factory = client.app.state.test_session_factory

    async def backdate():
        async with factory() as session:
            await session.execute(
                text(
                    "UPDATE orders SET created_at = now() - interval '31 minutes' "
                    "WHERE id = :oid"
                ),
                {"oid": order_id},
            )
            await session.commit()

    asyncio.run(backdate())


def test_pay_expired_order_rejected_and_restocked(client):
    """超时防线：过期的 PENDING 订单不能支付，自动取消 + 回补库存。"""
    _, user_headers, pid = _setup(client, stock=5)
    order_id = _create_order(client, user_headers, pid, quantity=2).json()["id"]
    _expire_order(client, order_id)

    r = client.post(f"/api/orders/{order_id}/pay", headers=user_headers)
    assert r.status_code == 409
    assert "超时" in r.json()["message"]

    detail = client.get(f"/api/orders/{order_id}", headers=user_headers).json()
    assert detail["status"] == "cancelled"
    assert client.get(f"/api/products/{pid}").json()["stock"] == 5  # 已回补


def test_sweeper_cancels_expired_and_restocks(client):
    """后台清扫：超时 PENDING 订单被取消，库存回补。"""
    _, user_headers, pid = _setup(client, stock=5)
    order_id = _create_order(client, user_headers, pid, quantity=2).json()["id"]
    _expire_order(client, order_id)
    assert client.get(f"/api/products/{pid}").json()["stock"] == 3  # 扣了还没回补

    factory = client.app.state.test_session_factory

    async def sweep():
        async with factory() as session:
            return await service.cancel_expired(session)

    assert asyncio.run(sweep()) == 1
    detail = client.get(f"/api/orders/{order_id}", headers=user_headers).json()
    assert detail["status"] == "cancelled"
    assert client.get(f"/api/products/{pid}").json()["stock"] == 5  # 回补


def test_sweeper_skips_fresh_orders(client):
    """未超时的订单不受清扫影响。"""
    _, user_headers, pid = _setup(client)
    order_id = _create_order(client, user_headers, pid).json()["id"]

    factory = client.app.state.test_session_factory

    async def sweep():
        async with factory() as session:
            return await service.cancel_expired(session)

    assert asyncio.run(sweep()) == 0
    detail = client.get(f"/api/orders/{order_id}", headers=user_headers).json()
    assert detail["status"] == "pending"  # 还是待支付