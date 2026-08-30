"""请求 ID 中间件：为每个请求生成/透传 X-Request-ID。

作用：排查问题时，客户端报的 request_id 能精确关联到服务端日志。
- 请求带 X-Request-ID 头则沿用（网关/客户端生成），否则生成 uuid
- 写入 request.state（异常处理器可读）和响应头（客户端可回传）
"""
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
