"""结构化日志工具。

设计目标：
- 使用 JSON 日志，便于被 ELK/ClickHouse/云日志平台解析
- 在入口统一脱敏，避免泄露 cookie/token/password 等敏感信息
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

# 日志字段名不区分大小写，命中后统一替换为掩码值。
SENSITIVE_KEYS = {
    "password",
    "cookie",
    "cookie_header",
    "set-cookie",
    "authorization",
    "token",
    "html",
    "response_html",
}


class JsonFormatter(logging.Formatter):
    """将日志记录格式化为单行 JSON。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "fields"):
            payload.update(getattr(record, "fields"))
        return json.dumps(payload, ensure_ascii=True, default=str)


def configure_logging(level: str = "INFO") -> None:
    """配置根日志器。

    该函数会重置已有 handler，保证不同运行环境下日志格式一致。
    """
    root = logging.getLogger()
    root.setLevel(level)

    for handler in list(root.handlers):
        root.removeHandler(handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(JsonFormatter())
    root.addHandler(stream_handler)


def _sanitize_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    """对扩展字段做敏感信息脱敏。"""
    cleaned: Dict[str, Any] = {}
    for key, value in fields.items():
        if key.lower() in SENSITIVE_KEYS:
            cleaned[key] = "***REDACTED***"
        else:
            cleaned[key] = value
    return cleaned


def log_event(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    """记录结构化业务事件日志。"""
    logger.log(level, message, extra={"fields": _sanitize_fields(fields)})
