"""全局 Redis 客户端。

- 用 redis.asyncio：本项目全 async，绝不能引入同步客户端（会卡死事件循环）
- get_redis 必须是 async：如果写成同步函数，FastAPI 的 Depends 会把它
  丢进线程池执行——线程池里没有事件循环，会直接报 "no running event loop"
- 连接绑定事件循环：事件循环变化时自动重建（pytest 每个测试一个新循环）
"""
import asyncio

from redis.asyncio import Redis

from app.core.config import get_settings

settings = get_settings()

_redis: Redis | None = None
_loop: asyncio.AbstractEventLoop | None = None


async def get_redis() -> Redis:
    """获取当前事件循环的客户端（不存在或循环变了就重建）。"""
    global _redis, _loop
    loop = asyncio.get_running_loop()
    if _redis is None or _loop is not loop or _loop.is_closed():
        _redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        _loop = loop
    return _redis


async def init_redis() -> Redis:
    """lifespan 启动时调用（生产：整个进程一个循环，只建一次）。"""
    return await get_redis()


async def close_redis() -> None:
    """lifespan 关闭时调用。

    容错：客户端可能属于其他事件循环（测试场景），跨循环关闭会报
    "Event loop is closed"——直接丢弃引用，交给解释器进程退出时清理。
    """
    global _redis, _loop
    client, loop = _redis, _loop
    _redis, _loop = None, None
    if client is None:
        return
    try:
        if loop is not None and loop is asyncio.get_running_loop():
            await client.aclose()
    except RuntimeError:
        pass  # 跨循环/已关闭循环：进程退出时清理
