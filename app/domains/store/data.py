"""store 领域数据访问：原子扣减、条件状态迁移、回补库存都在这里。

并发安全的关键：把条件写进 UPDATE 语句，让数据库来串行化，
而不是"先 SELECT 判断再 UPDATE"（那是竞态）。
"""
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domains.store.models import Order, Product

# ---------------- 查 ----------------

async def get_product_by_id(session: AsyncSession, product_id: int) -> Product | None:
    return await session.get(Product, product_id)


async def list_products(
    session: AsyncSession, limit: int, offset: int
) -> tuple[list[Product], int]:
    """分页查询：返回（当前页商品, 总条数）。

    LIMIT/OFFSET + 主键索引：只读一页，不再全表扫描（压测暴露的瓶颈）。
    """
    total = await session.scalar(select(func.count()).select_from(Product)) or 0
    result = await session.scalars(
        select(Product).order_by(Product.id).limit(limit).offset(offset)
    )
    return list(result), total


async def get_order_by_id(session: AsyncSession, order_id: int) -> Order | None:
    """取订单（带 items）。

    注意 selectinload：异步会话里 lazy load 会抛 MissingGreenlet，
    关联对象必须显式预加载。
    """
    return await session.scalar(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )


async def list_orders_by_user(session: AsyncSession, user_id: int) -> list[Order]:
    result = await session.scalars(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.user_id == user_id)
        .order_by(Order.id.desc())
    )
    return list(result)


# ---------------- 改（并发安全的原子操作） ----------------

async def deduct_stock(session: AsyncSession, product_id: int, quantity: int) -> bool:
    """原子扣减库存：条件写进 UPDATE，由数据库保证不超卖。

    返回 False = 库存不足（或商品不存在），调用方负责回滚事务。
    """
    result = await session.execute(
        update(Product)
        .where(Product.id == product_id, Product.stock >= quantity)
        .values(stock=Product.stock - quantity)
    )
    return result.rowcount == 1


async def add_stock(session: AsyncSession, product_id: int, quantity: int) -> None:
    """回补库存（取消订单时）。"""
    await session.execute(
        update(Product)
        .where(Product.id == product_id)
        .values(stock=Product.stock + quantity)
    )


async def transition_order_status(
    session: AsyncSession, order_id: int, from_status: str, to_status: str
) -> bool:
    """条件状态迁移：只有 from_status 才能变成 to_status。

    返回 False = 当前状态不允许迁移（并发下由数据库行锁保证只有一个成功）。
    """
    result = await session.execute(
        update(Order)
        .where(Order.id == order_id, Order.status == from_status)
        .values(status=to_status)
    )
    return result.rowcount == 1


async def save(session: AsyncSession, obj) -> object:
    """写操作统一收尾：提交。

    注意：不要 refresh——refresh 会把对象属性标记过期，之后访问
    懒加载关系（order.items）会触发 MissingGreenlet。
    expire_on_commit=False 时，提交后的对象保留全部属性，可直接返回。
    """
    await session.commit()
    return obj
