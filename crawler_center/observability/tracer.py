from __future__ import annotations

import asyncio
import logging
import traceback
import uuid
from dataclasses import dataclass
from typing import Mapping, Optional

from crawler_center.observability.backend import TraceBackend
from crawler_center.observability.context import _Tokens, reset_trace_context, set_trace_context, snapshot
from crawler_center.observability.models import STATUS_OK, Span, _utcnow
from crawler_center.observability.w3c import new_span_id, new_trace_id

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TraceSnapshot:
    trace_id: str
    span_id: str
    parent_span_id: str
    request_id: str


def current_snapshot() -> TraceSnapshot:
    trace_id, span_id, parent_span_id, request_id = snapshot()
    return TraceSnapshot(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        request_id=request_id,
    )


def ensure_snapshot(base: Optional[TraceSnapshot] = None) -> TraceSnapshot:
    source = base or current_snapshot()
    trace_id = source.trace_id or new_trace_id()
    request_id = source.request_id or uuid.uuid4().hex
    return TraceSnapshot(
        trace_id=trace_id,
        span_id=source.span_id,
        parent_span_id=source.parent_span_id,
        request_id=request_id,
    )


def start_span(
    *,
    service_name: str,
    stage: str,
    name: str,
    kind: str,
    tags: Optional[Mapping[str, object]] = None,
    parent_span_id: Optional[str] = None,
    base_snapshot: Optional[TraceSnapshot] = None,
    bind_context: bool = False,
) -> tuple[Span, Optional[_Tokens]]:
    trace_snapshot = ensure_snapshot(base_snapshot)
    resolved_parent_span_id = (
        parent_span_id.strip()
        if parent_span_id is not None
        else trace_snapshot.span_id.strip()
    )
    span_id = new_span_id()
    tokens: Optional[_Tokens] = None
    if bind_context:
        tokens = set_trace_context(
            trace_id=trace_snapshot.trace_id,
            span_id=span_id,
            parent_span_id=resolved_parent_span_id,
            request_id=trace_snapshot.request_id,
        )

    normalized_tags = {
        str(key): str(value)
        for key, value in (tags or {}).items()
        if value is not None and str(value) != ""
    }
    span = Span(
        span_id=span_id,
        parent_span_id=resolved_parent_span_id,
        trace_id=trace_snapshot.trace_id,
        request_id=trace_snapshot.request_id,
        service=service_name.strip() or "crawler_center",
        stage=stage.strip(),
        name=name.strip(),
        kind=kind.strip(),
        start_at=_utcnow(),
        tags=normalized_tags,
    )
    return span, tokens


def finish_span(
    span: Span,
    *,
    status: str = STATUS_OK,
    error_code: str = "",
    message: str = "",
    error_stack: str = "",
    extra_tags: Optional[Mapping[str, object]] = None,
) -> Span:
    if extra_tags:
        for key, value in extra_tags.items():
            if value is None:
                continue
            text = str(value)
            if text == "":
                continue
            span.tags[str(key)] = text
    if error_stack:
        span.error_stack = error_stack
    span.finish(status=status, error_code=error_code, message=message)
    return span


def reset_tokens(tokens: Optional[_Tokens]) -> None:
    if tokens is None:
        return
    try:
        reset_trace_context(tokens)
    except ValueError:
        logger.debug("skip resetting trace tokens across context boundary")


async def record_span_safe(backend: Optional[TraceBackend], span: Optional[Span]) -> None:
    if backend is None or span is None:
        return
    try:
        await backend.record_span(span)
    except Exception:
        logger.warning("record trace span failed: %s", span.name, exc_info=True)


def schedule_record_span(backend: Optional[TraceBackend], span: Optional[Span]) -> None:
    if backend is None or span is None:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("skip trace span without running loop: %s", span.name)
        return
    loop.create_task(record_span_safe(backend, span))


def format_exception_stack(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
