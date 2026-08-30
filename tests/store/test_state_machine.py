"""订单状态机测试：完整链路 + 非法迁移 + 权限 + 回补库存。"""
import asyncio

from app.core.redis import get_redis
from tests.conftest import make_admin
from tests.store.test_store import _create_order, _create_product, _register


def _setup(client, stock=10):
    """admin + 商品 + 用户，返回 (admin_headers, user_headers, product_id)。"""
    admin_id, admin_headers = _register(client, "admin")
    make_admin(client, admin_id)
    product = _create_product(client, admin_headers, stock=stock)
    _, user_headers = _register(client, "bob")
    return admin_headers, user_headers, product["id"]


def _order(client, user_headers, product_id, qty=1):
    return _create_order(client, user_headers, product_id, quantity=qty).json()["id"]


def _pay(client, user_headers, order_id):
    return client.post(f"/api/orders/{order_id}/pay", headers=user_headers)


def _stock(client, product_id):
    # 断言"当前库存"必须走详情接口：列表缓存允许滞后（设计），详情永远新鲜
    return client.get(f"/api/products/{product_id}").json()["stock"]


def test_full_state_machine_flow(client):
    """完整链路：下单→支付→发货→完成。"""
    admin_headers, user_headers, pid = _setup(client)
    order_id = _order(client, user_headers, pid)

    assert _pay(client, user_headers, order_id).json()["status"] == "paid"
    assert (
        client.post(f"/api/orders/{order_id}/ship", headers=admin_headers).json()["status"]
        == "shipped"
    )
    assert (
        client.post(f"/api/orders/{order_id}/complete", headers=admin_headers).json()["status"]
        == "completed"
    )


def test_refund_restocks_inventory(client):
    """退款：PAID→REFUNDED，库存回补（和取消同构）。"""
    admin_headers, user_headers, pid = _setup(client, stock=5)
    order_id = _order(client, user_headers, pid, qty=2)
    assert _stock(client, pid) == 3  # 5-2

    _pay(client, user_headers, order_id)
    r = client.post(f"/api/orders/{order_id}/refund", headers=admin_headers)
    assert r.json()["status"] == "refunded"
    assert _stock(client, pid) == 5  # 回补


def test_invalid_transitions_rejected(client):
    """状态机之外的迁移全部 409。"""
    admin_headers, user_headers, pid = _setup(client)
    order_id = _order(client, user_headers, pid)

    # 未支付不能发货 / 未发货不能完成 / 未支付不能退款
    assert client.post(f"/api/orders/{order_id}/ship", headers=admin_headers).status_code == 409
    assert (
        client.post(f"/api/orders/{order_id}/complete", headers=admin_headers).status_code == 409
    )
    assert client.post(f"/api/orders/{order_id}/refund", headers=admin_headers).status_code == 409

    # 支付后不能取消，但可以退款
    _pay(client, user_headers, order_id)
    assert client.post(f"/api/orders/{order_id}/cancel", headers=user_headers).status_code == 409
    assert client.post(f"/api/orders/{order_id}/refund", headers=admin_headers).status_code == 200


def test_admin_only_operations(client):
    """发货/完成/退款仅管理员。"""
    admin_headers, user_headers, pid = _setup(client)
    order_id = _order(client, user_headers, pid)
    _pay(client, user_headers, order_id)

    assert client.post(f"/api/orders/{order_id}/ship", headers=user_headers).status_code == 403
    assert (
        client.post(f"/api/orders/{order_id}/complete", headers=user_headers).status_code == 403
    )
    assert client.post(f"/api/orders/{order_id}/refund", headers=user_headers).status_code == 403


def test_refund_invalidates_detail_cache(client):
    """退款回补库存 → 商品详情缓存失效（同取消）。"""
    admin_headers, user_headers, pid = _setup(client, stock=5)

    async def detail_exists():
        return await (await get_redis()).exists(f"store:product:{pid}") == 1

    client.get(f"/api/products/{pid}")
    assert asyncio.run(detail_exists()) is True

    order_id = _order(client, user_headers, pid)
    _pay(client, user_headers, order_id)
    client.post(f"/api/orders/{order_id}/refund", headers=admin_headers)

    assert asyncio.run(detail_exists()) is False
