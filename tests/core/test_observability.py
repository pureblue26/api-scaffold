"""可观测性测试：Prometheus 指标 + JSON 结构化日志。"""
import json
import logging

from app.core.logging import JsonFormatter


def test_metrics_endpoint_records_requests(client):
    """访问接口后，/api/metrics 里出现对应的请求计数与耗时。"""
    # 制造一次请求（health 是 /api/health 路由）
    client.get("/api/health")
    r = client.get("/api/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]

    body = r.text
    # RED 三件套：总请求数 + 耗时直方图
    assert 'http_requests_total' in body
    assert 'http_request_duration_seconds' in body
    # 刚才那次 /api/health 被记录（方法/路径/状态 200）
    assert 'method="GET",path="/api/health",status="200"' in body


def test_metrics_normalizes_path_params(client):
    """路径归一化：带参数的路径不产生高基数标签。"""
    client.get("/api/products/99999")  # 404，路径含 id
    r = client.get("/api/metrics")
    # 出现的是路由模板 /api/products/{product_id}，不是 /api/products/99999
    assert 'path="/api/products/{product_id}"' in r.text
    assert 'path="/api/products/99999"' not in r.text


def test_json_log_formatter_produces_machine_readable_line():
    """JSON 日志：每行是可解析的 JSON，且带 request_id 字段。"""
    record = logging.LogRecord(
        name="scaffold",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="订单 %s 已创建",
        args=(42,),
        exc_info=None,
    )
    record.request_id = "trace-abc"
    line = JsonFormatter().format(record)
    parsed = json.loads(line)
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "scaffold"
    assert parsed["request_id"] == "trace-abc"
    assert parsed["message"] == "订单 42 已创建"
