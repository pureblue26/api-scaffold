"""请求 ID 中间件（纯 ASGI）：生成/透传 X-Request-ID。

- 请求带 X-Request-ID 头则沿用（网关/客户端生成），否则生成 uuid
- 写入 scope.state（异常处理器可读）和响应头（客户端可回传）
- 注入 contextvar（logging.py 的过滤器自动附加到日志）
- 用纯 ASGI 而非 BaseHTTPMiddleware：异常路径的响应也自动带头
  （BaseHTTPMiddleware 的后置逻辑对异常响应不可靠——我们踩过）
"""
import uuid

from app.core.logging import request_id_var


class RequestIdMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        request_id = headers.get(b"x-request-id", b"").decode() or uuid.uuid4().hex
        # 注入 scope.state（request.state 可读）与 contextvar（日志可带）
        scope.setdefault("state", {})["request_id"] = request_id
        request_id_var.set(request_id)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append(
                    (b"x-request-id", request_id.encode())
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)
