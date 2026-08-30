"""store 缓存测试：Cache Aside（命中/miss/失效）+ 穿透空值缓存。"""
import asyncio

from app.core.redis import get_redis
from tests.conftest import make_admin
from tests.store.test_store import _create_order, _create_product, _register


async def _redis_exists(key: str) -> bool:
    return await (await get_redis()).exists(key) == 1


async def _redis_get(key: str) -> str | None:
    return await (await get_redis()).get(key)


def test_products_list_cached_and_invalidated_on_create(client):
    admin_id, admin_headers = _register(client, "admin")
    make_admin(client, admin_id)

    client.get("/api/products")  # 第一次请求：miss → 查 DB → 回填缓存
    assert asyncio.run(_redis_exists("store:products")) == 1

    _create_product(client, admin_headers)  # 写路径：删缓存
    assert asyncio.run(_redis_exists("store:products")) == 0


def test_product_detail_cached_and_penetration_cache(client):
    admin_id, admin_headers = _register(client, "admin")
    make_admin(client, admin_id)
    product = _create_product(client, admin_headers)

    r = client.get(f"/api/products/{product['id']}")
    assert r.status_code == 200
    assert asyncio.run(_redis_exists(f"store:product:{product['id']}")) == 1

    # 穿透防护：不存在的 id 也缓存空值（短 TTL），避免反复打 DB
    client.get("/api/products/99999")
    assert asyncio.run(_redis_exists("store:product:99999")) == 1
    assert asyncio.run(_redis_get("store:product:99999")) == ""


def test_order_invalidates_list_and_detail_cache(client):
    admin_id, admin_headers = _register(client, "admin")
    make_admin(client, admin_id)
    product = _create_product(client, admin_headers, stock=5)
    _, user_headers = _register(client, "bob")

    client.get("/api/products")
    client.get(f"/api/products/{product['id']}")
    assert asyncio.run(_redis_exists("store:products")) == 1
    assert asyncio.run(_redis_exists(f"store:product:{product['id']}")) == 1

    _create_order(client, user_headers, product["id"])  # 库存变了：缓存失效
    assert asyncio.run(_redis_exists("store:products")) == 0
    assert asyncio.run(_redis_exists(f"store:product:{product['id']}")) == 0
