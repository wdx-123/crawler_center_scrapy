"""W3C Trace Context (traceparent / tracestate) 解析与构建。

实现严格遵循 W3C Trace Context Level 1 规范：
https://www.w3.org/TR/trace-context/

与 Go 侧 pkg/observability/w3c/w3c.go 保持一致。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional, Tuple

_HEX_RE = re.compile(r"^[0-9a-f]+$")
_ZERO_TRACE_ID = "0" * 32
_ZERO_SPAN_ID = "0" * 16
_DEFAULT_VERSION = "00"
_DEFAULT_FLAGS = "01"


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    span_id: str
    trace_flags: str = _DEFAULT_FLAGS
    trace_state: str = ""


def _is_hex(value: str, length: int) -> bool:
    return len(value) == length and _HEX_RE.match(value) is not None


def is_valid_trace_id(v: str) -> bool:
    v = v.strip().lower()
    return _is_hex(v, 32) and v != _ZERO_TRACE_ID


def is_valid_span_id(v: str) -> bool:
    v = v.strip().lower()
    return _is_hex(v, 16) and v != _ZERO_SPAN_ID


def new_trace_id() -> str:
    """生成 16 字节随机 trace_id (32 hex)。"""
    while True:
        tid = os.urandom(16).hex()
        if tid != _ZERO_TRACE_ID:
            return tid


def new_span_id() -> str:
    """生成 8 字节随机 span_id (16 hex)。"""
    while True:
        sid = os.urandom(8).hex()
        if sid != _ZERO_SPAN_ID:
            return sid


def parse_traceparent(header: str) -> Tuple[Optional[TraceContext], bool]:
    """解析 traceparent header。

    返回 (TraceContext, ok)。解析失败时返回 (None, False)。
    """
    parts = header.strip().split("-")
    if len(parts) != 4:
        return None, False

    version = parts[0].strip().lower()
    trace_id = parts[1].strip().lower()
    span_id = parts[2].strip().lower()
    flags = parts[3].strip().lower()

    if not _is_hex(version, 2) or version == "ff":
        return None, False
    if not is_valid_trace_id(trace_id):
        return None, False
    if not is_valid_span_id(span_id):
        return None, False
    if not _is_hex(flags, 2):
        return None, False

    return TraceContext(trace_id=trace_id, span_id=span_id, trace_flags=flags), True


def build_traceparent(tc: TraceContext) -> str:
    """构造 traceparent header 字符串。

    tc 不合法时返回空字符串。
    """
    trace_id = tc.trace_id.strip().lower()
    span_id = tc.span_id.strip().lower()
    flags = normalize_trace_flags(tc.trace_flags)

    if not is_valid_trace_id(trace_id) or not is_valid_span_id(span_id):
        return ""
    return f"{_DEFAULT_VERSION}-{trace_id}-{span_id}-{flags}"


def normalize_trace_flags(flags: str) -> str:
    flags = flags.strip().lower()
    if not _is_hex(flags, 2):
        return _DEFAULT_FLAGS
    return flags
