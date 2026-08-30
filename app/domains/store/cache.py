"""store 领域缓存：Cache Aside 模式 + 缓存三兄弟防护。

- Cache Aside：读走缓存，miss 查 DB 回填；写路径必须删缓存（不是更新！）
- 穿透防护：loader 返回 None 也缓存空值（短 TTL），避免不存在的数据反复打 DB
- 击穿防护：SETNX 互斥锁，热点 key 过期只让一个请求重建
- 雪崩防护：TTL 加随机抖动，避免大量 key 同时过期
- CACHE_ENABLED=False：读路径直查 DB（压测 A/B、故障演练用）
"""
import asyncio
import json
import random

from app.core.config import get_settings
from app.core.redis import get_redis
from app.domains.store import data
from app.domains.store.schemas import ProductOut

settings = get_settings()

PRODUCTS_LIST_KEY = "store:products"
PRODUCT_LIST_TTL = 60  # 秒


async def _get_or_set(key: str, ttl: int, loader, *, cache_none: bool = False):
    """通用缓存助手：命中直接返回；miss 时互斥重建。

    loader 必须返回可 JSON 序列化的数据（dict/list）。
    """
    if not settings.CACHE_ENABLED:
        # 缓存总开关关闭（压测 A/B / 故障演练）：直查 DB，不读不写 Redis
        return await loader()

    redis = await get_redis()
    val = await redis.get(key)
    if val is not None:
        return json.loads(val) if val else None  # "" 空值缓存 → None

    # 击穿防护：SETNX 拿锁，抢不到就等重建者写完再读一次
    lock_key = f"{key}:lock"
    acquired = await redis.set(lock_key, "1", nx=True, ex=5)
    if not acquired:
        await asyncio.sleep(0.05)
        val = await redis.get(key)
        return json.loads(val) if val else None

    try:
        data_out = await loader()
        if data_out is None:
            if cache_none:
                await redis.set(key, "", ex=ttl)  # 穿透防护：空值也缓存
            return None
        # 雪崩防护：TTL 加随机抖动
        await redis.set(key, json.dumps(data_out), ex=ttl + random.randint(0, 30))
        return data_out
    finally:
        await redis.delete(lock_key)


async def get_products_cached(session) -> list[dict]:
    """商品列表缓存。返回 dict 列表，由 router 转 ProductOut。"""

    async def loader():
        products = await data.list_products(session)
        return [ProductOut.model_validate(p).model_dump(mode="json") for p in products]

    return (await _get_or_set(PRODUCTS_LIST_KEY, PRODUCT_LIST_TTL, loader)) or []


async def get_product_cached(session, product_id: int) -> dict | None:
    """单个商品缓存（含穿透空值缓存）。"""

    async def loader():
        product = await data.get_product_by_id(session, product_id)
        if product is None:
            return None
        return ProductOut.model_validate(product).model_dump(mode="json")

    return await _get_or_set(f"store:product:{product_id}", 60, loader, cache_none=True)


async def invalidate_products() -> None:
    """写路径统一失效入口：建商品 / 下单 / 取消 都必须调用。

    只删列表缓存；单商品缓存按需单独删（避免全量删）。
    """
    await (await get_redis()).delete(PRODUCTS_LIST_KEY)


async def invalidate_product(product_id: int) -> None:
    await (await get_redis()).delete(f"store:product:{product_id}")
