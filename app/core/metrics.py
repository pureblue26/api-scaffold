"""Prometheus 指标：RED 方法（Rate 请求率 / Errors 错误 / Duration 耗时）。

用纯 ASGI 中间件而不是 BaseHTTPMiddleware：
- BaseHTTPMiddleware 的异常路径不走后置逻辑（我们踩过：request-id 头丢失）
- 纯 ASGI 包住 send，无论响应从哪来（含异常处理器）都能观测

路径归一化：用 scope["route"] 拿路由模板（/api/orders/123 → /api/orders/{order_id}），
避免高基数标签（每个订单 id 都成一个指标标签会打爆 Prometheus）。
"""
import time

from prometheus_client import Counter, Histogram

# 三个核心指标（RED）
REQUESTS_TOTAL = Counter(
    "http_requests_total", "HTTP 请求总数", ["method", "path", "status"]
)
REQUESTS_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP 请求耗时（秒）",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)


def _normalized_path(scope: dict) -> str:
    """路径归一化：用路由模板替换实际路径中的参数。

    路由模板可能不含 include_router 挂载前缀（/api/orders/123 的模板是
    /orders/{order_id}）——用路由的静态前缀在实际路径里定位挂载前缀，
    补全成完整 URL 模板：/api/orders/{order_id}。
    避免高基数标签（每个订单 id 一个标签会打爆 Prometheus）。
    """
    route = scope.get("route")
    route_path = getattr(route, "path", None)
    if not route_path:
        return scope.get("path", "/unknown")

    actual = scope.get("path", "")
    static_prefix = route_path.split("{")[0]  # 模板的静态部分，如 "/orders/"
    idx = actual.find(static_prefix)
    if idx > 0:
        return actual[:idx] + route_path  # 补全挂载前缀
    return route_path


class MetricsMiddleware:
    """纯 ASGI 中间件：观测每个 HTTP 请求的状态码与耗时。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if scope.get("path") == "/api/metrics":  # 不观测指标端点自身
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "UNKNOWN")
        status = {"code": 500}
        start = time.perf_counter()

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            status["code"] = 500  # 未处理异常（正常应被 500 处理器接住）
            raise
        finally:
            duration = time.perf_counter() - start
            # 注意：路径归一化必须在 app 跑完之后做——
            # 此时路由已匹配，scope["route"] 才可用（测试抓到过这个时序 bug）
            path = _normalized_path(scope)
            REQUESTS_TOTAL.labels(method, path, str(status["code"])).inc()
            REQUESTS_DURATION.labels(method, path).observe(duration)
