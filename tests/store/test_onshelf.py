"""商品上下架测试：列表过滤 / 详情 410 / 缓存标记 / 权限 / shelved_at 语义。"""
import asyncio
import json

from sqlalchemy import select

from app.core.redis import get_redis
from app.domains.store.models import Product
from tests.conftest import make_admin
from tests.store.test_store import _create_product, _register


def _setup(client, stock=10):
    admin_id, admin_headers = _register(client, "admin")
    make_admin(client, admin_id)
    product = _create_product(client, admin_headers, stock=stock)
    _, user_headers = _register(client, "bob")
    return admin_headers, user_headers, product["id"]


async def _redis_get(key):
    return await (await get_redis()).get(key)


def _list_ids(client):
    return [p["id"] for p in client.get("/api/products").json()["items"]]


def test_delist_and_relist_full_cycle(client):
    admin_headers, _, pid = _setup(client)

    # 下架：列表消失 + 详情 410
    r = client.post(f"/api/products/{pid}/delist", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["is_active"] is False
    assert pid not in _list_ids(client)
    assert client.get(f"/api/products/{pid}").status_code == 410

    # 上架：列表恢复 + 详情 200
    r = client.post(f"/api/products/{pid}/relist", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["is_active"] is True
    assert pid in _list_ids(client)
    assert client.get(f"/api/products/{pid}").status_code == 200


def test_delist_requires_admin(client):
    _, user_headers, pid = _setup(client)
    assert client.post(f"/api/products/{pid}/delist", headers=user_headers).status_code == 403


def test_delist_not_found(client):
    admin_id, admin_headers = _register(client, "admin")
    make_admin(client, admin_id)
    assert client.post("/api/products/99999/delist", headers=admin_headers).status_code == 404


def test_delisted_detail_uses_cache_marker(client):
    """下架写"已下架"标记：详情命中标记返回 410，零数据库访问。"""
    admin_headers, _, pid = _setup(client)
    client.get(f"/api/products/{pid}")  # 预热详情缓存

    client.post(f"/api/products/{pid}/delist", headers=admin_headers)
    # 标记已写入（不是删掉）
    val = asyncio.run(_redis_get(f"store:product:{pid}"))
    assert json.loads(val) == "DELISTED"

    assert client.get(f"/api/products/{pid}").status_code == 410


def test_relist_clears_delisted_marker(client):
    admin_headers, _, pid = _setup(client)
    client.post(f"/api/products/{pid}/delist", headers=admin_headers)
    client.post(f"/api/products/{pid}/relist", headers=admin_headers)

    # 标记被删除 → 详情回到正常
    assert asyncio.run(_redis_get(f"store:product:{pid}")) is None
    assert client.get(f"/api/products/{pid}").status_code == 200


def test_shelved_at_only_on_real_activation(client):
    """shelved_at 只在"下架→上架"时更新；重复上架不刷新。"""
    admin_headers, _, pid = _setup(client)
    factory = client.app.state.test_session_factory

    async def get_shelved_at():
        async with factory() as session:
            product = await session.scalar(select(Product).where(Product.id == pid))
            return product.shelved_at

    first = asyncio.run(get_shelved_at())
    assert first is not None  # 创建即上架，有初始时间

    # 重复上架已上架的商品：shelved_at 不变
    client.post(f"/api/products/{pid}/relist", headers=admin_headers)
    assert asyncio.run(get_shelved_at()) == first

    # 下架再上架：shelved_at 更新
    client.post(f"/api/products/{pid}/delist", headers=admin_headers)
    client.post(f"/api/products/{pid}/relist", headers=admin_headers)
    assert asyncio.run(get_shelved_at()) > first
