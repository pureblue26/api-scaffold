"""JSON 结构化日志 + request_id 全链路注入。

为什么 JSON 日志：生产环境日志要能机读查询（ELK/Loki/Grafana），
一行 JSON 比一行文本值钱——可按 level/logger/request_id 精确过滤。
request_id 用 contextvar 注入：中间件设置后，同一次请求的所有日志
（含异常处理器、业务代码）自动带上 request_id，无需手动传参。
"""
import contextvars
import json
import logging

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """把 contextvar 里的 request_id 附加到每条日志记录。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """输出单行 JSON：{ts, level, logger, request_id, message, exc?}"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: int = logging.INFO) -> None:
    """配置根 logger：JSON 格式 + request_id 过滤器。"""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
