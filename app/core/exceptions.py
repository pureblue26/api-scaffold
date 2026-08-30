"""业务异常分类：API 层统一映射为 HTTP 状态码。

新增业务异常时，继承 AppError 的子类即可，无需再改 main.py——
register_exception_handlers 会自动注册所有子类。
"""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("scaffold")


class AppError(Exception):
    """所有业务异常的基类：detail 会作为响应体的 message 返回。"""

    status_code: int = 500
    detail: str = "服务器内部错误"

    def __init__(self, detail: str | None = None):
        self.detail = detail or self.detail
        super().__init__(self.detail)


class NotFoundError(AppError):
    status_code = 404
    detail = "资源不存在"


class ConflictError(AppError):
    status_code = 409
    detail = "资源状态冲突"


class UnauthorizedError(AppError):
    status_code = 401
    detail = "未认证"


class ForbiddenError(AppError):
    status_code = 403
    detail = "无权限"


class BadRequestError(AppError):
    status_code = 400
    detail = "请求参数错误"


class TooManyRequestsError(AppError):
    """限流触发（429）。"""

    status_code = 429
    detail = "请求过于频繁"


def _request_id(request: Request) -> str:
    """取请求 ID（同步函数：中间件未跑到时兜底为 "-"）。"""
    return getattr(request.state, "request_id", "-")


async def handle_unhandled(request: Request, exc: Exception) -> JSONResponse:
    """兜底 500：记录日志（含 request_id/路径）并返回可追踪的 request_id。

    之前的问题：未处理异常只返回通用 500，线上无法关联日志。
    """
    request_id = _request_id(request)
    logger.error(
        "未处理异常 | request_id=%s | path=%s | %s: %s",
        request_id,
        request.url.path,
        type(exc).__name__,
        exc,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    response = JSONResponse(
        status_code=500,
        content={"message": "服务器内部错误", "request_id": request_id},
    )
    response.headers["X-Request-ID"] = request_id
    return response


def register_exception_handlers(app: FastAPI) -> None:
    """把 AppError 的所有子类 + 兜底 500 注册为 FastAPI 异常处理器。"""

    async def handler(request: Request, exc: AppError) -> JSONResponse:
        # 所有业务错误都带上 request_id，客户端可拿它反馈给后端排查
        # 注意：异常路径不走中间件后置逻辑，响应头这里直接加
        request_id = _request_id(request)
        response = JSONResponse(
            status_code=exc.status_code,
            content={"message": exc.detail, "request_id": request_id},
        )
        response.headers["X-Request-ID"] = request_id
        return response

    for exc_type in AppError.__subclasses__():
        app.add_exception_handler(exc_type, handler)

    # 兜底：任何未处理异常 → 500（日志已记录，响应带 request_id）
    app.add_exception_handler(Exception, handle_unhandled)
