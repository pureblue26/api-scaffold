"""store 业务逻辑：编排 data 层的原子操作，只关心业务规则。"""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis import get_redis
from app.domains.auth.models import User
from app.domains.store import cache, data
from app.domains.store.exceptions import (
    InsufficientStockError,
    InvalidOrderStateError,
    OrderNotFoundError,
    ProductNotFoundError,
)
from app.domains.store.models import Order, OrderItem, OrderStatus, Product
from app.domains.store.schemas import OrderItemIn

settings = get_settings()


def _is_expired(order: Order) -> bool:
    """订单是否超过支付时限（只对 PENDING 有意义）。"""
    timeout = timedelta(minutes=settings.ORDER_TIMEOUT_MINUTES)
    return order.created_at + timeout < datetime.now(UTC)


async def create_product(session: AsyncSession, name: str, price: int, stock: int) -> Product:
    product = Product(name=name, price=price, stock=stock)
    session.add(product)
    saved = await data.save(session, product)
    await cache.invalidate_products()  # 缓存失效：新商品立即可见
    return saved


async def update_product(
    session: AsyncSession,
    product_id: int,
    name: str | None = None,
    price: int | None = None,
    stock: int | None = None,
) -> Product:
    """改商品（仅管理员）。

    缓存失效比订单严格：名称/价格变了，列表里必须及时可见（版本+1），
    不能像订单那样容忍库存滞后——"改了什么"决定"失效策略"。
    注意：stock 是覆盖式写入（管理员权威修正）。与下单原子扣减并发时，
    管理员写入可能覆盖刚扣的库存——这是权威操作的有意取舍。
    """
    product = await data.get_product_by_id(session, product_id)
    if product is None:
        raise ProductNotFoundError()

    if name is not None:
        product.name = name
    if price is not None:
        product.price = price
    if stock is not None:
        product.stock = stock

    saved = await data.save(session, product)
    await cache.invalidate_products()  # 名称/价格变了：列表必须失效
    await cache.invalidate_product(product_id)  # 详情也失效
    return saved


async def list_products(session: AsyncSession) -> list[Product]:
    return await data.list_products(session)


async def create_order(session: AsyncSession, user: User, items: list[OrderItemIn]) -> Order:
    """下单：整个订单一个事务——任何一个商品扣不动，全部回滚。

    并发安全：不预检查库存，直接用原子扣减（条件写进 UPDATE）。
    两个订单同时买最后一个商品时，数据库只让一个成功。
    """
    order_items: list[OrderItem] = []
    total = 0
    for item in items:
        # 先查一次只为区分"商品不存在"和"库存不足"的报错；正确性不靠这个查询
        product = await data.get_product_by_id(session, item.product_id)
        if product is None:
            await session.rollback()
            raise ProductNotFoundError(f"商品 {item.product_id} 不存在")

        product_name = product.name  # rollback 会过期已加载对象，先取值备用
        ok = await data.deduct_stock(session, item.product_id, item.quantity)
        if not ok:
            await session.rollback()  # 前面扣成功的商品一起回滚
            raise InsufficientStockError(f"商品 {item.product_id}（{product_name}）库存不足")

        order_items.append(
            OrderItem(
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=product.price,  # 价格快照
            )
        )
        total += product.price * item.quantity

    order = Order(user_id=user.id, total_amount=total, items=order_items)
    session.add(order)
    saved = await data.save(session, order)
    # 库存变了：只失效涉及商品的【详情】缓存（决策页必须精确）。
    # 【列表】缓存不失效——靠 TTL 自然过期，避免下单风暴反复重建列表
    for item in order_items:
        await cache.invalidate_product(item.product_id)
    return saved


async def get_order(session: AsyncSession, order_id: int, user: User) -> Order:
    """订单详情：本人或管理员可见；他人订单当"不存在"处理（防泄露）。"""
    order = await data.get_order_by_id(session, order_id)
    if order is None or (order.user_id != user.id and user.role != "admin"):
        raise OrderNotFoundError()
    return order


async def list_user_orders(
    session: AsyncSession, user_id: int, limit: int, offset: int
) -> tuple[list[Order], int]:
    return await data.list_orders_by_user(session, user_id, limit, offset)


async def pay_order(
    session: AsyncSession, order_id: int, user: User, payment_id: str | None = None
) -> Order:
    """支付：PENDING → PAID（幂等）。

    两层幂等：
    1. 状态幂等（核心）：已 PAID 的订单再次支付返回当前状态（200），
       不是 409——"重复达成已达成的结果"算成功；CANCELLED 仍 409。
    2. 幂等键去重（Redis SETNX）：带 payment_id 时，同一支付流水只处理
       一次，防止网关回调重放/并发重复。键存 24h，TTL 自动清理。

    超时防线：过期的 PENDING 订单【不能支付】——先自动取消（回补库存）
    再拒绝。防止"30 分钟后回来，订单已超时却支付成功"。
    """
    order = await get_order(session, order_id, user)

    # 幂等键去重：同一支付流水号只允许绑定一个订单
    if payment_id:
        redis = await get_redis()
        dedup_key = f"payment:{payment_id}"
        if not await redis.set(dedup_key, str(order_id), nx=True, ex=86400):
            prev_order = await redis.get(dedup_key)
            if prev_order != str(order_id):
                raise InvalidOrderStateError("支付流水号已被其他订单使用")
            # 同一订单重放：幂等返回当前状态
            return order

    # 超时防线
    if order.status == OrderStatus.PENDING.value and _is_expired(order):
        await _restock_order_core(
            session, order, OrderStatus.PENDING, OrderStatus.CANCELLED, "订单已超时取消"
        )
        raise InvalidOrderStateError("订单已超时取消，无法支付")

    # 状态幂等：已是 PAID，直接返回（重复支付 = 成功）
    if order.status == OrderStatus.PAID.value:
        return order

    ok = await data.transition_order_status(
        session, order_id, OrderStatus.PENDING.value, OrderStatus.PAID.value
    )
    if not ok:
        await session.rollback()
        raise InvalidOrderStateError("只有待支付订单可以支付")
    await session.commit()
    return await data.get_order_by_id(session, order_id)


async def _restock_order_core(
    session: AsyncSession,
    order: Order,
    from_status: OrderStatus,
    to_status: OrderStatus,
    error_msg: str,
) -> Order:
    """取消/退款/超时清理的公共核心：条件迁移 + 回补库存 + 失效详情缓存。

    前提：调用方已持有 Order 对象并完成所有权/存在性检查。
    from_status 必须【显式传入】，不能信 order.status——
    否则 cancel 会把 paid 订单也取消（状态机约束被破坏，测试抓到过）。
    """
    ok = await data.transition_order_status(
        session, order.id, from_status.value, to_status.value
    )
    if not ok:
        await session.rollback()
        raise InvalidOrderStateError(error_msg)

    for item in order.items:
        await data.add_stock(session, item.product_id, item.quantity)
    await session.commit()
    order = await data.get_order_by_id(session, order.id)
    for item in order.items:
        await cache.invalidate_product(item.product_id)  # 详情缓存失效，列表靠 TTL
    return order


async def cancel_order(session: AsyncSession, order_id: int, user: User) -> Order:
    """取消：PENDING → CANCELLED，回补库存。"""
    order = await get_order(session, order_id, user)  # 所有权/存在性检查
    return await _restock_order_core(
        session, order, OrderStatus.PENDING, OrderStatus.CANCELLED, "只有待支付订单可以取消"
    )


async def refund_order(session: AsyncSession, order_id: int, user: User) -> Order:
    """退款：PAID → REFUNDED，回补库存（已支付订单的"撤销"）。"""
    order = await get_order(session, order_id, user)
    return await _restock_order_core(
        session, order, OrderStatus.PAID, OrderStatus.REFUNDED, "只有已支付订单可以退款"
    )


async def ship_order(session: AsyncSession, order_id: int, user: User) -> Order:
    """发货：PAID → SHIPPED（管理员）。库存保持扣减状态。"""
    await get_order(session, order_id, user)  # 所有权/存在性检查
    ok = await data.transition_order_status(
        session, order_id, OrderStatus.PAID.value, OrderStatus.SHIPPED.value
    )
    if not ok:
        await session.rollback()
        raise InvalidOrderStateError("只有已支付订单可以发货")
    await session.commit()
    return await data.get_order_by_id(session, order_id)


async def complete_order(session: AsyncSession, order_id: int, user: User) -> Order:
    """完成：SHIPPED → COMPLETED（管理员）。"""
    await get_order(session, order_id, user)  # 所有权/存在性检查
    ok = await data.transition_order_status(
        session, order_id, OrderStatus.SHIPPED.value, OrderStatus.COMPLETED.value
    )
    if not ok:
        await session.rollback()
        raise InvalidOrderStateError("只有已发货订单可以完成")
    await session.commit()
    return await data.get_order_by_id(session, order_id)


async def cancel_expired(session: AsyncSession) -> int:
    """取消所有超时的 PENDING 订单（回补库存），返回处理数量。

    由后台任务周期性调用；幂等——并发下已处理的订单条件迁移失败会被跳过。
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.ORDER_TIMEOUT_MINUTES)
    expired_ids = list(
        await session.scalars(
            select(Order.id).where(
                Order.status == OrderStatus.PENDING.value,
                Order.created_at < cutoff,
            )
        )
    )
    count = 0
    for order_id in expired_ids:
        order = await data.get_order_by_id(session, order_id)
        if order is None:
            continue
        try:
            await _restock_order_core(
        session, order, OrderStatus.PENDING, OrderStatus.CANCELLED, "订单已超时"
    )
            count += 1
        except InvalidOrderStateError:
            pass  # 并发下已被用户取消/其他清扫处理，跳过
    return count
