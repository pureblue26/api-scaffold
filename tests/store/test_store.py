"""store 领域测试：商品/订单 CRUD + 两个并发竞态（原子扣减、取消vs支付）。"""
import asyncio

import httpx

from app.main import app
from tests.conftest import make_admin


def _register(client, username, password="password123"):
    r = client.post("/api/auth/register", json={"username": username, "password": password})
    assert r.status_code == 201, r.text
    token = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    ).json()["access_token"]
    return r.json()["id"], {"Authorization": f"Bearer {token}"}


def _create_product(client, headers, name="Book", price=1999, stock=10):
    r = client.post(
        "/api/products", json={"name": name, "price": price, "stock": stock}, headers=headers
    )
    assert r.status_code == 201, r.text
    return r.json()


def _create_order(client, headers, product_id, quantity=1):
    return client.post(
        "/api/orders",
        json={"items": [{"product_id": product_id, "quantity": quantity}]},
        headers=headers,
    )


# ---------------- 商品 ----------------

def test_create_product_requires_admin(client):
    _, headers = _register(client, "alice")
    r = client.post("/api/products", json={"name": "X", "price": 1, "stock": 1}, headers=headers)
    assert r.status_code == 403


# ---------------- 订单正常流 ----------------

def test_create_order_deducts_stock_and_snapshot_price(client):
    admin_id, admin_headers = _register(client, "admin")
    make_admin(client, admin_id)
    product = _create_product(client, admin_headers, price=1999, stock=5)
    _, user_headers = _register(client, "bob")

    r = _create_order(client, user_headers, product["id"], quantity=2)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending"
    assert body["total_amount"] == 1999 * 2
    assert body["items"][0]["unit_price"] == 1999  # 价格快照
    assert client.get("/api/products").json()["items"][0]["stock"] == 3  # 5-2


def test_create_order_insufficient_stock(client):
    admin_id, admin_headers = _register(client, "admin")
    make_admin(client, admin_id)
    product = _create_product(client, admin_headers, stock=1)
    _, user_headers = _register(client, "bob")

    r = _create_order(client, user_headers, product["id"], quantity=2)
    assert r.status_code == 409
    assert "库存不足" in r.json()["message"]
    # 整单回滚：库存不变
    assert client.get("/api/products").json()["items"][0]["stock"] == 1


def test_order_not_visible_to_others(client):
    admin_id, admin_headers = _register(client, "admin")
    make_admin(client, admin_id)
    product = _create_product(client, admin_headers, stock=5)
    _, alice_headers = _register(client, "alice")
    _, bob_headers = _register(client, "bob")

    order = _create_order(client, alice_headers, product["id"]).json()
    r = client.get(f"/api/orders/{order['id']}", headers=bob_headers)
    assert r.status_code == 404  # 他人订单当不存在，不泄露


# ---------------- 状态机 ----------------

def test_pay_order_and_pay_twice_rejected(client):
    admin_id, admin_headers = _register(client, "admin")
    make_admin(client, admin_id)
    product = _create_product(client, admin_headers)
    _, user_headers = _register(client, "bob")
    order_id = _create_order(client, user_headers, product["id"]).json()["id"]

    r = client.post(f"/api/orders/{order_id}/pay", headers=user_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "paid"

    r = client.post(f"/api/orders/{order_id}/pay", headers=user_headers)
    assert r.status_code == 409  # PAID 不能再支付


def test_cancel_order_restocks(client):
    admin_id, admin_headers = _register(client, "admin")
    make_admin(client, admin_id)
    product = _create_product(client, admin_headers, stock=5)
    _, user_headers = _register(client, "bob")
    order_id = _create_order(client, user_headers, product["id"], quantity=2).json()["id"]

    r = client.post(f"/api/orders/{order_id}/cancel", headers=user_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    assert client.get("/api/products").json()["items"][0]["stock"] == 5  # 回补


def test_cancel_after_pay_rejected(client):
    admin_id, admin_headers = _register(client, "admin")
    make_admin(client, admin_id)
    product = _create_product(client, admin_headers)
    _, user_headers = _register(client, "bob")
    order_id = _create_order(client, user_headers, product["id"]).json()["id"]

    client.post(f"/api/orders/{order_id}/pay", headers=user_headers)
    r = client.post(f"/api/orders/{order_id}/cancel", headers=user_headers)
    assert r.status_code == 409  # PAID 不能取消


# ---------------- 并发竞态 ----------------

def test_concurrent_orders_last_item_only_one_wins(client):
    """两个用户同时买最后一个商品：原子扣减保证一成一败。"""
    admin_id, admin_headers = _register(client, "admin")
    make_admin(client, admin_id)
    product = _create_product(client, admin_headers, stock=1)
    _, alice_headers = _register(client, "alice")
    _, bob_headers = _register(client, "bob")

    async def race():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            r1, r2 = await asyncio.gather(
                ac.post(
                    "/api/orders",
                    json={"items": [{"product_id": product["id"], "quantity": 1}]},
                    headers=alice_headers,
                ),
                ac.post(
                    "/api/orders",
                    json={"items": [{"product_id": product["id"], "quantity": 1}]},
                    headers=bob_headers,
                ),
            )
            return r1, r2

    r1, r2 = asyncio.run(race())
    statuses = sorted([r1.status_code, r2.status_code])
    assert statuses == [201, 409], f"期望一成一败，实际 {statuses}"
    assert client.get("/api/products").json()["items"][0]["stock"] == 0  # 库存只扣了一次


def test_concurrent_pay_and_cancel_only_one_wins(client):
    """同一个订单同时支付和取消：条件状态迁移保证只有一个成功。"""
    admin_id, admin_headers = _register(client, "admin")
    make_admin(client, admin_id)
    product = _create_product(client, admin_headers)
    _, user_headers = _register(client, "bob")
    order_id = _create_order(client, user_headers, product["id"]).json()["id"]

    async def race():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            r1, r2 = await asyncio.gather(
                ac.post(f"/api/orders/{order_id}/pay", headers=user_headers),
                ac.post(f"/api/orders/{order_id}/cancel", headers=user_headers),
            )
            return r1, r2

    r1, r2 = asyncio.run(race())
    statuses = sorted([r1.status_code, r2.status_code])
    assert statuses == [200, 409], f"期望一成一败，实际 {statuses}"
    final = client.get(f"/api/orders/{order_id}", headers=user_headers).json()
    # 赢家要么 paid 要么 cancelled
    assert final["status"] in ("paid", "cancelled")
    # 若取消，库存回补；若支付，库存仍扣着
    stock = client.get("/api/products").json()["items"][0]["stock"]
    # 商品默认库存 10，下单扣 1：cancelled 回补到 10，paid 保持 9
    assert stock == (10 if final["status"] == "cancelled" else 9)