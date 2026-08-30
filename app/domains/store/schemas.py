"""库存/订单领域请求/响应模型。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domains.store.models import OrderStatus


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    price: int = Field(ge=0, description="单价（分）")
    stock: int = Field(ge=0)


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price: int
    stock: int


class OrderItemIn(BaseModel):
    product_id: int
    quantity: int = Field(ge=1)


class OrderCreate(BaseModel):
    items: list[OrderItemIn] = Field(min_length=1)


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    quantity: int
    unit_price: int


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: OrderStatus
    total_amount: int
    created_at: datetime
    items: list[OrderItemOut]
