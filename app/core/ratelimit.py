"""通用限流依赖：固定窗口计数（INCR + EXPIRE），按 IP + 路径限流。

原理：每个请求 INCR 计数，第一次请求设置窗口过期时间，超过上限返回 429。
Redis 的 INCR/EXPIRE 是原子命令，并发下计数不会错。

进阶（真实流量时再看）：固定窗口的缺陷是窗口边界会突刺，
滑动窗口用 ZSet 实现，精确但多花内存——先固定窗口够用。
"""
from fastapi import Depends, Request
from redis.asyncio import Redis

from app.core.exceptions import TooManyRequestsError
from app.core.redis import get_redis


def rate_limit(limit: int, window: int):
    """限流依赖工厂。

    用法：dependencies=[Depends(rate_limit(5, 60))]  # 同一 IP 5 次/分钟
    """

    async def dependency(request: Request, redis: Redis = Depends(get_redis)) -> None:
        key = f"rate:{request.url.path}:{request.client.host}"
        count = await redis.incr(key)          # 原子自增
        if count == 1:
            await redis.expire(key, window)    # 窗口从第一次请求起算
        if count > limit:
            raise TooManyRequestsError(f"请求过于频繁，请 {window} 秒后再试")

    return dependency
