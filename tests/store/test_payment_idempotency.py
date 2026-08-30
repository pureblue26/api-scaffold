"""支付幂等测试：状态幂等 + 幂等键（payment_id）去重。"""
from tests.conftest import make_admin
from tests.store.test_store import _create_order, _create_product, _register


def _setup(client, stock=10):
    admin_id, admin_headers = _register(client, "admin")
    make_admin(client, admin_id)
    product = _create_product(client, admin_headers, stock=stock)
    _, user_headers = _register(client, "bob")
    return admin_headers, user_headers, product["id"]


def _pay(client, user_headers, order_id, payment_id=None):
    body = {"payment_id": payment_id} if payment_id else None
    return client.post(f"/api/orders/{order_id}/pay", headers=user_headers, json=body)


def test_same_payment_id_replay_is_idempotent(client):
    """同一支付流水号重放：返回 200，不重复处理、不报错。"""
    _, user_headers, pid = _setup(client)
    order_id = _create_order(client, user_headers, pid).json()["id"]

    first = _pay(client, user_headers, order_id, "txn-0001")
    assert first.status_code == 200
    assert first.json()["status"] == "paid"

    # 重放同一流水号：幂等成功
    replay = _pay(client, user_headers, order_id, "txn-0001")
    assert replay.status_code == 200
    assert replay.json()["status"] == "paid"


def test_payment_id_cannot_reuse_across_orders(client):
    """同一支付流水号不能用于两个订单（防重放攻击）。"""
    _, user_headers, pid = _setup(client, stock=10)
    order_a = _create_order(client, user_headers, pid).json()["id"]
    order_b = _create_order(client, user_headers, pid).json()["id"]

    assert _pay(client, user_headers, order_a, "txn-0002").status_code == 200
    r = _pay(client, user_headers, order_b, "txn-0002")
    assert r.status_code == 409
    assert "流水号" in r.json()["message"]
    # 订单 B 保持待支付
    assert client.get(f"/api/orders/{order_b}", headers=user_headers).json()["status"] == "pending"


def test_pay_cancelled_order_still_rejected(client):
    """状态机仍然严格：CANCELLED 订单不能支付（幂等不等于无脑成功）。"""
    _, user_headers, pid = _setup(client)
    order_id = _create_order(client, user_headers, pid).json()["id"]
    client.post(f"/api/orders/{order_id}/cancel", headers=user_headers)

    r = _pay(client, user_headers, order_id)
    assert r.status_code == 409
