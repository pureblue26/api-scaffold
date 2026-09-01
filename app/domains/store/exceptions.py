"""store 领域异常。"""
from app.core.exceptions import AppError


class ProductNotFoundError(AppError):
    status_code = 404
    detail = "商品不存在"


class ProductDelistedError(AppError):
    """商品已下架。410 Gone：HTTP 规范里"资源曾经可用，现在永久不可用"。"""

    status_code = 410
    detail = "商品已下架"


class InsufficientStockError(AppError):
    """库存不足：并发下单时靠原子扣减触发，不是预检查。"""

    status_code = 409
    detail = "商品库存不足"


class OrderNotFoundError(AppError):
    """订单不存在，或不属于当前用户（不泄露他人订单存在性）。"""

    status_code = 404
    detail = "订单不存在"


class InvalidOrderStateError(AppError):
    """状态机不允许的迁移（如支付后再取消）。"""

    status_code = 409
    detail = "订单当前状态不允许此操作"
