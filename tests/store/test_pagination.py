"""分页测试：页大小/偏移/总数/边界校验。"""
from tests.conftest import make_admin
from tests.store.test_store import _create_order, _create_product, _register


def _make_products(client, count=5):
    admin_id, admin_headers = _register(client, "admin")
    make_admin(client, admin_id)
    for i in range(count):
        _create_product(client, admin_headers, name=f"商品{i}", price=100 + i, stock=100)
    return admin_headers


def test_pagination_pages_and_total(client):
    _make_products(client, 5)

    r = client.get("/api/products?limit=2&offset=0")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 2
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert body["has_more"] is True

    # 最后一页：剩 1 条，没有下一页
    r = client.get("/api/products?limit=2&offset=4")
    body = r.json()
    assert len(body["items"]) == 1
    assert body["has_more"] is False


def test_pagination_defaults(client):
    _make_products(client, 3)
    # 不带参数：limit 默认 20，返回全部 3 条
    r = client.get("/api/products")
    body = r.json()
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert len(body["items"]) == 3
    assert body["has_more"] is False


def test_pagination_validation(client):
    assert client.get("/api/products?limit=0").status_code == 422   # 小于 1
    assert client.get("/api/products?limit=101").status_code == 422  # 超过 100
    assert client.get("/api/products?offset=-1").status_code == 422  # 负数


# ---------------- 订单分页 ----------------

def test_orders_pagination(client):
    admin_id, admin_headers = _register(client, "admin")
    make_admin(client, admin_id)
    product = _create_product(client, admin_headers, stock=100)
    _, user_headers = _register(client, "alice")

    for _ in range(5):  # alice 下 5 单
        _create_order(client, user_headers, product["id"])

    r = client.get("/api/orders?limit=2&offset=0", headers=user_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 2
    assert body["total"] == 5
    assert body["has_more"] is True
    # 最新在前（id 倒序）
    assert body["items"][0]["id"] > body["items"][1]["id"]

    # 最后一页：剩 1 条，没有下一页
    r = client.get("/api/orders?limit=2&offset=4", headers=user_headers)
    body = r.json()
    assert len(body["items"]) == 1
    assert body["has_more"] is False


def test_orders_pagination_isolated_per_user(client):
    """订单是私有数据：alice 下 3 单，bob 的列表是空的。"""
    admin_id, admin_headers = _register(client, "admin")
    make_admin(client, admin_id)
    product = _create_product(client, admin_headers, stock=100)
    _, alice_headers = _register(client, "alice")
    _, bob_headers = _register(client, "bob")

    for _ in range(3):
        _create_order(client, alice_headers, product["id"])

    assert client.get("/api/orders", headers=alice_headers).json()["total"] == 3
    assert client.get("/api/orders", headers=bob_headers).json()["total"] == 0

    # 未登录不能看订单列表
    assert client.get("/api/orders").status_code == 401

