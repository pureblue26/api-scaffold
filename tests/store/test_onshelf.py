"""商品上下架测试（你写的第二个功能配套测试）——测试逻辑由你实现。

【测试原则】每个测试验证一个行为；用 准备(Arrange) → 执行(Act) → 断言(Assert) 三段式。
当前这些函数是占位（会抛 NotImplementedError），跑 pytest 是红的——
你的任务是把它们填成真实断言，填完后应该全绿。

【可用的工具】：
- client 夹具（conftest）：每个测试一个干净的测试环境
- make_admin(client, user_id)：把用户提升为管理员
- _register(client, username) → (user_id, headers)：注册并登录
- _create_product(client, headers, name=..., price=..., stock=...) → 商品 dict
- 查 Redis：asyncio.run(_redis_get("store:product:1"))（_redis_get 已定义）
- 查数据库：client.app.state.test_session_factory（_get_shelved_at 已定义）
"""
import asyncio
import json

from sqlalchemy import select

from app.core.redis import get_redis
from app.domains.store.models import Product
from tests.conftest import make_admin
from tests.store.test_store import _create_product, _register


def _setup(client, stock=10):
    """准备：管理员 + 商品 + 普通用户，返回 (admin_headers, user_headers, product_id)。"""
    admin_id, admin_headers = _register(client, "admin")
    make_admin(client, admin_id)
    product = _create_product(client, admin_headers, stock=stock)
    _, user_headers = _register(client, "bob")
    return admin_headers, user_headers, product["id"]


async def _redis_get(key: str):
    return await (await get_redis()).get(key)


async def _get_shelved_at(client, product_id):
    """从数据库读 shelved_at（ProductOut 不暴露它，直接查库）。"""
    factory = client.app.state.test_session_factory
    async with factory() as session:
        product = await session.scalar(select(Product).where(Product.id == product_id))
        return product.shelved_at


def _list_ids(client) -> list[int]:
    """当前商品列表里的所有 id。"""
    return [p["id"] for p in client.get("/api/products").json()["items"]]


# ---------------- 你的测试（填 TODO）----------------

def test_delist_and_relist_full_cycle(client):
    """完整周期：下架后列表消失+详情 410；上架后列表恢复+详情 200。"""
    # TODO: 用 _setup 拿 headers 和 pid
    # 1. 下架 → 断言 200 且 is_active 为 False
    # 2. 断言 pid 不在 _list_ids(client) 里
    # 3. 断言 GET /api/products/{pid} 返回 410
    # 4. 上架 → 断言 200 且 is_active 为 True
    # 5. 断言 pid 回到 _list_ids(client)
    # 6. 断言详情返回 200
    admin_headers, user_headers, pid = _setup(client)
    r = client.post(f"/api/products/{pid}/delist",headers=admin_headers)
    assert r.status_code == 200 
    r_body = r.json()
    assert r_body["is_active"] is False
    assert pid not in _list_ids(client) ,f"❌ PID {pid} 在列表中"
    assert client.get(f"/api/products/{pid}", headers=admin_headers).status_code == 410
    assert client.get(f"/api/products/{pid}", headers=user_headers).status_code == 410
    s  = client.post(f"/api/products/{pid}/relist", headers=admin_headers)
    s_body = s.json()
    assert s_body["is_active"] is True
    assert pid  in _list_ids(client),f"❌ PID {pid} 不在列表中"
    assert client.get(f"/api/products/{pid}").status_code == 200



def test_delist_requires_admin(client):
    """普通用户不能下架商品（403）。"""
    # TODO: _setup 拿 user_headers 和 pid，用 user_headers 调 delist，断言 403
    admin_headers, user_headers, pid = _setup(client)
    assert client.post(f"/api/products/{pid}/delist", headers=user_headers).status_code == 403
    assert client.post(f"/api/products/{pid}/delist", headers=admin_headers).status_code == 200



def test_delist_not_found(client):
    """下架不存在的商品 → 404。"""
    # TODO: 注册管理员并提升，对 /api/products/99999/delist 断言 404
    admin_headers, _, _ = _setup(client)
    assert client.post("/api/products/99999/delist", headers=admin_headers).status_code == 404




def test_delisted_detail_uses_cache_marker(client):
    """下架写"已下架"标记：详情命中标记返回 410，不查数据库。"""
    # TODO:
    # 1. _setup 拿 admin_headers 和 pid，先 GET 详情预热缓存
    # 2. 下架
    # 3. 断言 asyncio.run(_redis_get(f"store:product:{pid}")) 反序列化后等于 "DELISTED"
    #    提示：标记存的是 json.dumps("DELISTED")，读出来要 json.loads
    # 4. 断言详情仍返回 410（这次是命中缓存标记，没查库）
    admin_headers, user_headers, pid = _setup(client)
    assert client.get(f"/api/products/{pid}", headers=user_headers).status_code == 200
    assert client.post(f"/api/products/{pid}/delist", headers=admin_headers).status_code == 200
    val = asyncio.run(_redis_get(f"store:product:{pid}"))
    assert json.loads(val) == "DELISTED"
    assert client.get(f"/api/products/{pid}", headers=admin_headers).status_code == 410
    assert client.get(f"/api/products/{pid}", headers=user_headers).status_code == 410


def test_relist_clears_delisted_marker(client):
    """上架清除"已下架"标记：详情恢复正常。"""
    # TODO:
    # 1. _setup → 下架 → 上架
    # 2. 断言 asyncio.run(_redis_get(f"store:product:{pid}")) is None（标记没了）
    # 3. 断言详情返回 200
    admin_headers, user_headers, pid = _setup(client)
    assert client.post(f"/api/products/{pid}/delist", headers=admin_headers).status_code == 200
    assert client.post(f"/api/products/{pid}/relist", headers=admin_headers).status_code == 200
    assert asyncio.run(_redis_get(f"store:product:{pid}")) is None
    assert client.get(f"/api/products/{pid}", headers=admin_headers).status_code == 200
    assert client.get(f"/api/products/{pid}", headers=user_headers).status_code == 200
    assert client.get(f"/api/products/{pid}").status_code == 200


def test_shelved_at_only_on_real_activation(client):
    """shelved_at 只在"下架→上架"时更新；重复上架不刷新。"""
    # TODO:
    # 1. _setup 拿 admin_headers 和 pid，读初始 shelved_at（_get_shelved_at）
    # 2. 重复上架已上架的商品 → 断言 shelved_at 不变
    # 3. 下架再上架 → 断言 shelved_at 比初始值大（更新了）
    admin_headers, user_headers, pid = _setup(client)
    client.post(f"/api/products/{pid}/relist", headers=admin_headers)
    old_timestamp = asyncio.run(_get_shelved_at(client, pid))
    client.post(f"/api/products/{pid}/relist", headers=admin_headers)
    new_timestamp = asyncio.run(_get_shelved_at(client, pid))
    assert new_timestamp == old_timestamp
    client.post(f"/api/products/{pid}/delist", headers=admin_headers)
    client.post(f"/api/products/{pid}/relist", headers=admin_headers)
    time_stamp = asyncio.run(_get_shelved_at(client, pid))
    assert time_stamp > old_timestamp
    