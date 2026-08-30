"""订单超时清理：后台任务（lifespan 启动，进程生命周期内循环）。

原理：定期扫描超时的 PENDING 订单并取消（回补库存）。
- 复用 service.cancel_expired，与用户取消同一套并发安全逻辑
- 自己的 Session（不依赖请求作用域）
- 任何一轮失败只记日志不中断循环（保证持续运行）
"""
import asyncio
import logging

from app.database.base import SessionFactory
from app.domains.store import service

logger = logging.getLogger("scaffold")

SWEEP_INTERVAL_SECONDS = 60  # 扫描间隔


async def order_expiry_loop() -> None:
    """定期扫描超时 PENDING 订单并自动取消（回补库存）。"""
    while True:
        try:
            async with SessionFactory() as session:
                count = await service.cancel_expired(session)
            if count:
                logger.info("自动取消 %d 个超时订单", count)
        except asyncio.CancelledError:
            break  # 应用关闭
        except Exception:
            logger.exception("订单超时清理失败")  # 单轮失败不中断循环
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
