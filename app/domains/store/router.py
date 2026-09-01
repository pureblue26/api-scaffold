"""store 领域接口：商品 / 订单。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import get_session
from app.domains.auth.dependencies import get_current_user, require_admin
from app.domains.auth.models import User
from app.domains.store import cache, onshelf, service
from app.domains.store.exceptions import ProductDelistedError, ProductNotFoundError
from app.domains.store.schemas import (
    OrderCreate,
    OrderOut,
    PageOut,
    PayRequest,
    ProductCreate,
    ProductOut,
    ProductUpdate,
)

router = APIRouter(tags=["store"])


# ---------------- 商品 ----------------

@router.get("/products", response_model=PageOut[ProductOut])
async def products(
    limit: int = Query(default=20, ge=1, le=100, description="每页条数"),
    offset: int = Query(default=0, ge=0, description="跳过条数"),
    session: AsyncSession = Depends(get_session),
) -> PageOut[ProductOut]:
    """商品列表（分页 + Redis 缓存，miss 才查 DB；新建商品时版本号失效）。"""
    page = await cache.get_products_cached(session, limit, offset)
    items = [ProductOut.model_validate(p) for p in page["items"]]
    total = page["total"]
    return PageOut(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
    )


@router.get("/products/{product_id}", response_model=ProductOut)
async def product_detail(
    product_id: int, session: AsyncSession = Depends(get_session)
) -> ProductOut:
    """商品详情（走 Redis 缓存；已下架返回 410，命中缓存标记时不查库）。"""
    product = await cache.get_product_cached(session, product_id)
    if product == cache.DELISTED:
        raise ProductDelistedError()  # 410：已下架
    if product is None:
        raise ProductNotFoundError()
    return ProductOut.model_validate(product)


@router.post("/products/{product_id}/delist", response_model=ProductOut)
async def delist_product(
    product_id: int,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> ProductOut:
    """下架商品（仅管理员）：从列表消失，详情返回 410。"""
    product = await onshelf.set_product_active(session, product_id, False)
    if product is None:
        raise ProductNotFoundError()
    return ProductOut.model_validate(product)


@router.post("/products/{product_id}/relist", response_model=ProductOut)
async def relist_product(
    product_id: int,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> ProductOut:
    """上架商品（仅管理员）：回到列表，详情恢复正常。"""
    product = await onshelf.set_product_active(session, product_id, True)
    if product is None:
        raise ProductNotFoundError()
    return ProductOut.model_validate(product)


@router.post("/products", response_model=ProductOut, status_code=201)
async def create_product(
    data: ProductCreate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> ProductOut:
    """创建商品（仅管理员）。"""
    product = await service.create_product(session, data.name, data.price, data.stock)
    return ProductOut.model_validate(product)


@router.patch("/products/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: int,
    data: ProductUpdate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> ProductOut:
    """修改商品（仅管理员）。名称/价格/库存至少改一个。"""
    product = await service.update_product(
        session, product_id, name=data.name, price=data.price, stock=data.stock
    )
    return ProductOut.model_validate(product)


# ---------------- 订单 ----------------

@router.post("/orders", response_model=OrderOut, status_code=201)
async def create_order(
    data: OrderCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> OrderOut:
    """下单：原子扣库存，库存不足整单回滚（409）。"""
    order = await service.create_order(session, current_user, data.items)
    return OrderOut.model_validate(order)


@router.get("/orders", response_model=PageOut[OrderOut])
async def my_orders(
    limit: int = Query(default=20, ge=1, le=100, description="每页条数"),
    offset: int = Query(default=0, ge=0, description="跳过条数"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> PageOut[OrderOut]:
    """我的订单（分页）。

    注意：订单【不走缓存】——和商品列表相反。原因：
    1. 私有数据：每个用户只看自己的，缓存命中率天然低
    2. 频繁变动：下单/支付/取消都改它，缓存失效成本高
    3. 正确性敏感：订单状态必须实时，不能容忍"滞后"
    缓存不是万能的——读多写少才值得缓存。
    """
    orders, total = await service.list_user_orders(session, current_user.id, limit, offset)
    items = [OrderOut.model_validate(o) for o in orders]
    return PageOut(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
    )


@router.get("/orders/{order_id}", response_model=OrderOut)
async def order_detail(
    order_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> OrderOut:
    return OrderOut.model_validate(await service.get_order(session, order_id, current_user))


@router.post("/orders/{order_id}/pay", response_model=OrderOut)
async def pay_order(
    order_id: int,
    data: PayRequest | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> OrderOut:
    """支付（幂等）：重复支付返回当前状态；带 payment_id 时同一流水只处理一次。"""
    payment_id = data.payment_id if data else None
    return OrderOut.model_validate(
        await service.pay_order(session, order_id, current_user, payment_id)
    )


@router.post("/orders/{order_id}/cancel", response_model=OrderOut)
async def cancel_order(
    order_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> OrderOut:
    return OrderOut.model_validate(await service.cancel_order(session, order_id, current_user))


# ---------------- 订单状态机（管理员操作） ----------------

@router.post("/orders/{order_id}/ship", response_model=OrderOut)
async def ship_order(
    order_id: int,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> OrderOut:
    """发货：PAID → SHIPPED（仅管理员）。"""
    return OrderOut.model_validate(await service.ship_order(session, order_id, admin))


@router.post("/orders/{order_id}/complete", response_model=OrderOut)
async def complete_order(
    order_id: int,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> OrderOut:
    """完成：SHIPPED → COMPLETED（仅管理员）。"""
    return OrderOut.model_validate(await service.complete_order(session, order_id, admin))


@router.post("/orders/{order_id}/refund", response_model=OrderOut)
async def refund_order(
    order_id: int,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> OrderOut:
    """退款：PAID → REFUNDED，回补库存（仅管理员）。"""
    return OrderOut.model_validate(await service.refund_order(session, order_id, admin))
