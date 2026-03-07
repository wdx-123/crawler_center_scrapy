"""FastAPI 链路追踪中间件。

职责：
1. 从入站请求 header 提取 W3C traceparent / tracestate / X-Request-ID
2. 解析或生成 trace_id / span_id / parent_span_id / request_id
3. 写入 contextvars，供业务代码在 async 链路中访问
4. 请求结束后构建 Span 并推送到 TraceBackend
"""

from __future__ import annotations

import traceback
import uuid
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from crawler_center.observability.backend import TraceBackend
from crawler_center.observability.context import reset_trace_context, set_trace_context
from crawler_center.observability.models import STATUS_ERROR, STATUS_OK, Span, _utcnow
from crawler_center.observability.w3c import (
    new_span_id,
    new_trace_id,
    parse_traceparent,
)

HEADER_TRACEPARENT = "traceparent"
HEADER_TRACESTATE = "tracestate"
HEADER_REQUEST_ID = "x-request-id"


class TraceMiddleware(BaseHTTPMiddleware):
    """为每个 HTTP 请求创建 server span，自动提取 / 生成 W3C trace context。"""

    def __init__(
        self,
        app,
        *,
        backend: TraceBackend,
        service_name: str = "crawler_center",
    ) -> None:
        super().__init__(app)
        self._backend = backend
        self._service_name = service_name

    # 每个请求创建一个 server span
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id, parent_span_id, trace_state = self._extract_trace(request)
        span_id = new_span_id()
        request_id = (request.headers.get(HEADER_REQUEST_ID) or "").strip() or uuid.uuid4().hex

        if not trace_id:
            trace_id = new_trace_id()

        tokens = set_trace_context(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            request_id=request_id,
        )

        span = Span(
            span_id=span_id,
            parent_span_id=parent_span_id,
            trace_id=trace_id,
            request_id=request_id,
            service=self._service_name,
            stage="http.request",
            name=f"{request.method} {request.url.path}",
            kind="server",
            start_at=_utcnow(),
            tags={
                "http.method": request.method,
                "http.path": request.url.path,
            },
        )

        status_code: Optional[int] = None
        error_msg = ""
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception as exc:
            error_msg = str(exc)
            span.error_stack = traceback.format_exc()
            raise
        finally:
            if status_code is not None:
                span.tags["http.status_code"] = str(status_code)

            if error_msg or (status_code is not None and status_code >= 500):
                span.finish(
                    status=STATUS_ERROR,
                    error_code=str(status_code or 500),
                    message=error_msg or f"HTTP {status_code}",
                )
            else:
                span.finish(status=STATUS_OK)

            await self._backend.record_span(span)
            reset_trace_context(tokens)

    @staticmethod
    def _extract_trace(request: Request):
        """从请求 header 提取 W3C trace context。"""
        traceparent_raw = (request.headers.get(HEADER_TRACEPARENT) or "").strip()
        trace_state = (request.headers.get(HEADER_TRACESTATE) or "").strip()

        trace_id = ""
        parent_span_id = ""

        if traceparent_raw:
            tc, ok = parse_traceparent(traceparent_raw)
            if ok and tc is not None:
                trace_id = tc.trace_id
                parent_span_id = tc.span_id

        return trace_id, parent_span_id, trace_state
