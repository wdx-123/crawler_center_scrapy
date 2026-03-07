"""可观测性包：W3C Trace Context 传播 + Span 采集 + Redis Stream 推送。"""

from crawler_center.observability.context import (
    get_parent_span_id,
    get_request_id,
    get_span_id,
    get_trace_id,
    reset_trace_context,
    set_trace_context,
)
from crawler_center.observability.models import Span
from crawler_center.observability.w3c import build_traceparent, parse_traceparent

# 导出所有符号，方便其他模块导入
__all__ = [
    "Span",
    "build_traceparent",
    "get_parent_span_id",
    "get_request_id",
    "get_span_id",
    "get_trace_id",
    "parse_traceparent",
    "reset_trace_context",
    "set_trace_context",
]
