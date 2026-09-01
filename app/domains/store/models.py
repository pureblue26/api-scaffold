"""库存/订单领域 ORM 模型。

金额全部用"分"（int），绝不用 float——浮点会丢精度（0.1+0.2 != 0.3）。
"""
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class OrderStatus(str, Enum):
    """订单状态机：只允许图上的迁移，其他一律 409。

    PENDING ─支付▶ PAID ─发货▶ SHIPPED ─完成▶ COMPLETED
       │                │
       └─取消▶ CANCELLED   └─退款▶ REFUNDED
       （回补库存）         （回补库存）
    """

    PENDING = "pending"      # 待支付
    PAID = "paid"            # 已支付
    SHIPPED = "shipped"      # 已发货
    COMPLETED = "completed"  # 已完成
    CANCELLED = "cancelled"  # 已取消（回补库存）
    REFUNDED = "refunded"    # 已退款（回补库存）


class Product(BaseModel):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)  # 单位：分
    stock: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # 上架状态
    created_at: Mapped[datetime] = mapped_column(  # 创建时间（与 User/Order 保持一致）
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    shelved_at: Mapped[datetime | None] = mapped_column(  # 上架时间（null = 从未上架）
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        # 不变式 1：库存永远 >= 0，数据库兜底
        CheckConstraint("stock >= 0", name="ck_products_stock_non_negative"),
    )


class Order(BaseModel):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default=OrderStatus.PENDING.value, nullable=False)
    total_amount: Mapped[int] = mapped_column(Integer, nullable=False)  # 单位：分
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(BaseModel):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    # 价格快照：下单时的单价，商品改价不影响历史订单（不变式 5）
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False)

    order: Mapped[Order] = relationship(back_populates="items")

    __table_args__ = (
        # 不变式 4：同一订单同一商品只有一行
        UniqueConstraint("order_id", "product_id", name="uq_order_items_order_product"),
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
    )
