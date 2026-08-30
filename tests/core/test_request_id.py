"""request-id 中间件 + 500 兜底测试。"""
from fastapi.testclient import TestClient

from app.database.base import get_session
from app.main import app


def test_response_has_request_id_header(client):
    """每个响应都带 X-Request-ID；客户端自带的会沿用。"""
    r = client.get("/api/health")
    assert r.headers["X-Request-ID"]
    assert len(r.headers["X-Request-ID"]) == 32  # uuid4 hex

    # 客户端自带 ID：透传
    r = client.get("/api/health", headers={"X-Request-ID": "my-trace-001"})
    assert r.headers["X-Request-ID"] == "my-trace-001"


def test_unhandled_error_returns_500_with_request_id(client):
    """未处理异常 → 500 + request_id（日志可关联）。"""
    async def boom():
        raise RuntimeError("test boom")

    app.dependency_overrides[get_session] = boom
    tc = TestClient(app, raise_server_exceptions=False)
    try:
        r = tc.get("/api/products")
        assert r.status_code == 500
        body = r.json()
        assert body["message"] == "服务器内部错误"
        assert body["request_id"]  # 非空，可追踪
        assert r.headers["X-Request-ID"] == body["request_id"]  # 响应头一致
    finally:
        app.dependency_overrides.clear()


def test_business_error_includes_request_id(client):
    """业务错误（如 404）也带 request_id，客户端可反馈。"""
    r = client.get("/api/products/99999")
    assert r.status_code == 404
    assert r.json()["request_id"]
