"""库存/订单领域请求/响应模型。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domains.store.models import OrderStatus


class PageOut[T](BaseModel):  # Python 3.12 泛型语法（PEP 695）
    """通用分页响应：items + 总数 + 当前页参数 + 是否还有下一页。"""

    items: list[T]
    total: int
    limit: int
    offset: int
    has_more: bool


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    price: int = Field(ge=0, description="单价（分）")
    stock: int = Field(ge=0)


class ProductUpdate(BaseModel):
    """改商品：字段全部可选，但至少给一个；未知字段直接拒绝。"""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    price: int | None = Field(default=None, ge=0)
    stock: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "ProductUpdate":
        if self.name is None and self.price is None and self.stock is None:
            raise ValueError("至少提供一个要修改的字段")
        return self


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price: int
    stock: int
    is_active: bool = True  # 默认 True：兼容升级前缓存的旧数据


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


class PayRequest(BaseModel):
    """支付请求：可选携带支付流水号（幂等键，防网关回调重放/重复提交）。"""

    payment_id: str | None = Field(default=None, max_length=64)
