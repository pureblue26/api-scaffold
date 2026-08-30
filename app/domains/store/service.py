"""store 业务逻辑：编排 data 层的原子操作，只关心业务规则。"""
from sqlalchemy.ext.asyncio import AsyncSession

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
    # （压测实测：每次下单都删列表 → 重建尖峰 → P95 恶化）
    for item in order_items:
        await cache.invalidate_product(item.product_id)
    return saved


async def get_order(session: AsyncSession, order_id: int, user: User) -> Order:
    """订单详情：本人或管理员可见；他人订单当"不存在"处理（防泄露）。"""
    order = await data.get_order_by_id(session, order_id)
    if order is None or (order.user_id != user.id and user.role != "admin"):
        raise OrderNotFoundError()
    return order


async def list_user_orders(session: AsyncSession, user_id: int) -> list[Order]:
    return await data.list_orders_by_user(session, user_id)


async def pay_order(session: AsyncSession, order_id: int, user: User) -> Order:
    """支付：PENDING → PAID。简单迁移（网关回调/幂等后续再加）。"""
    order = await get_order(session, order_id, user)
    ok = await data.transition_order_status(
        session, order_id, OrderStatus.PENDING.value, OrderStatus.PAID.value
    )
    if not ok:
        await session.rollback()
        raise InvalidOrderStateError("只有待支付订单可以支付")
    await session.commit()
    # 状态是用 Core UPDATE 改的，内存对象还是旧值；重新取一遍（带 items）
    order = await data.get_order_by_id(session, order_id)
    return order


async def cancel_order(session: AsyncSession, order_id: int, user: User) -> Order:
    """取消：PENDING → CANCELLED，并回补库存。

    条件迁移保证并发安全：用户点取消的同时订单被支付了，
    迁移失败返回 409，不会出现"已支付的订单被取消"。
    """
    order = await get_order(session, order_id, user)
    ok = await data.transition_order_status(
        session, order_id, OrderStatus.PENDING.value, OrderStatus.CANCELLED.value
    )
    if not ok:
        await session.rollback()
        raise InvalidOrderStateError("只有待支付订单可以取消")

    # 回补库存（取消成功才回补，同一事务内）
    for item in order.items:
        await data.add_stock(session, item.product_id, item.quantity)
    await session.commit()
    order = await data.get_order_by_id(session, order_id)
    # 同下单：只失效详情缓存，列表靠 TTL
    for item in order.items:
        await cache.invalidate_product(item.product_id)
    return order
