"""业务异常分类：API 层统一映射为 HTTP 状态码。

新增业务异常时，继承 AppError 的子类即可，无需再改 main.py——
register_exception_handlers 会自动注册所有子类。
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


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


def register_exception_handlers(app: FastAPI) -> None:
    """把 AppError 的所有子类注册为 FastAPI 异常处理器。"""

    async def handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"message": exc.detail})

    for exc_type in AppError.__subclasses__():
        app.add_exception_handler(exc_type, handler)
