"""store 领域接口：商品 / 订单。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import get_session
from app.domains.auth.dependencies import get_current_user, require_admin
from app.domains.auth.models import User
from app.domains.store import service
from app.domains.store.schemas import (
    OrderCreate,
    OrderOut,
    ProductCreate,
    ProductOut,
)

router = APIRouter(tags=["store"])


# ---------------- 商品 ----------------

@router.get("/products", response_model=list[ProductOut])
async def products(session: AsyncSession = Depends(get_session)) -> list[ProductOut]:
    return [ProductOut.model_validate(p) for p in await service.list_products(session)]


@router.post("/products", response_model=ProductOut, status_code=201)
async def create_product(
    data: ProductCreate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> ProductOut:
    """创建商品（仅管理员）。"""
    product = await service.create_product(session, data.name, data.price, data.stock)
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


@router.get("/orders", response_model=list[OrderOut])
async def my_orders(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[OrderOut]:
    return [OrderOut.model_validate(o) for o in await service.list_user_orders(session, current_user.id)]


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
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> OrderOut:
    return OrderOut.model_validate(await service.pay_order(session, order_id, current_user))


@router.post("/orders/{order_id}/cancel", response_model=OrderOut)
async def cancel_order(
    order_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> OrderOut:
    return OrderOut.model_validate(await service.cancel_order(session, order_id, current_user))
