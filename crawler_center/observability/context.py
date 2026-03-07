"""基于 contextvars 的链路上下文传播。

在 async 调用链中安全传递 trace_id / span_id / parent_span_id / request_id，
无需手动透传参数，也不会在并发请求间串扰。
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Optional, Tuple

_trace_id_var: ContextVar[str] = ContextVar("obs_trace_id", default="")
_span_id_var: ContextVar[str] = ContextVar("obs_span_id", default="")
_parent_span_id_var: ContextVar[str] = ContextVar("obs_parent_span_id", default="")
_request_id_var: ContextVar[str] = ContextVar("obs_request_id", default="")


@dataclass(frozen=True)
class _Tokens:
    """set_trace_context 返回的 reset token 集合，供 reset_trace_context 使用。"""

    trace_id: Token[str]
    span_id: Token[str]
    parent_span_id: Token[str]
    request_id: Token[str]


def set_trace_context(
    *,
    trace_id: str = "",
    span_id: str = "",
    parent_span_id: str = "",
    request_id: str = "",
) -> _Tokens:
    """写入当前协程的链路上下文，返回 reset tokens。"""
    return _Tokens(
        trace_id=_trace_id_var.set(trace_id),
        span_id=_span_id_var.set(span_id),
        parent_span_id=_parent_span_id_var.set(parent_span_id),
        request_id=_request_id_var.set(request_id),
    )


def reset_trace_context(tokens: _Tokens) -> None:
    """恢复链路上下文到 set_trace_context 之前的状态。"""
    _trace_id_var.reset(tokens.trace_id)
    _span_id_var.reset(tokens.span_id)
    _parent_span_id_var.reset(tokens.parent_span_id)
    _request_id_var.reset(tokens.request_id)


def get_trace_id() -> str:
    return _trace_id_var.get()


def get_span_id() -> str:
    return _span_id_var.get()


def get_parent_span_id() -> str:
    return _parent_span_id_var.get()


def get_request_id() -> str:
    return _request_id_var.get()


def snapshot() -> Tuple[str, str, str, str]:
    """返回 (trace_id, span_id, parent_span_id, request_id) 快照。"""
    return (
        _trace_id_var.get(),
        _span_id_var.get(),
        _parent_span_id_var.get(),
        _request_id_var.get(),
    )
