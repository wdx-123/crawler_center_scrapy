from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Iterable, Iterator, Optional
from urllib.parse import urlsplit

from scrapy import Request

from crawler_center.observability.backend import TraceBackend
from crawler_center.observability.models import STATUS_ERROR, STATUS_OK, Span
from crawler_center.observability.tracer import (
    TraceSnapshot,
    current_snapshot,
    ensure_snapshot,
    finish_span,
    format_exception_stack,
    record_span_safe,
    reset_tokens,
    schedule_record_span,
    start_span,
)

# crawler 上保存 tracing session 的属性名
TRACE_SESSION_ATTR = "_obs_trace_session"

# request.meta 中用于传递 tracing 关系和运行态对象的 key
META_PARENT_SPAN_ID = "_obs_parent_span_id"
META_REQUEST_SPAN = "_obs_request_span"
META_REQUEST_SPAN_ID = "_obs_request_span_id"
META_CALLBACK_SCOPE = "_obs_callback_scope"

# 视为请求失败的 HTTP 状态码
ERROR_STATUS_CODES = {403, 407, 408, 429, 500, 502, 503, 504}


@dataclass
class CallbackScope:
    """单次 callback 执行期间的 tracing 上下文。"""
    span: Span
    tokens: Any
    callback_name: str
    finished: bool = False


class ScrapyTraceSession:
    """封装一次 spider 运行期间的 tracing 会话。"""

    def __init__(
        self,
        *,
        backend: TraceBackend,
        service_name: str,
        spider_name: str,
        target_site: str,
        trace_snapshot: TraceSnapshot,
    ) -> None:
        self.backend = backend
        self.service_name = service_name.strip() or "crawler_center"
        self.spider_name = spider_name.strip() or "unknown_spider"
        self.target_site = target_site.strip()
        self.trace_snapshot = ensure_snapshot(trace_snapshot)
        self.parent_span_id = self.trace_snapshot.span_id.strip()

        # run 级 span：覆盖整次 spider 运行
        self.run_span: Optional[Span] = None
        self.run_tokens: Any = None
        self.run_finished = False

    @classmethod
    def from_current_context(
        cls,
        *,
        backend: TraceBackend,
        service_name: str,
        spider_name: str,
        target_site: str,
    ) -> "ScrapyTraceSession":
        """基于当前上下文快照创建 tracing session。"""
        return cls(
            backend=backend,
            service_name=service_name,
            spider_name=spider_name,
            target_site=target_site,
            trace_snapshot=current_snapshot(),
        )

    @property
    def trace_id(self) -> str:
        return self.trace_snapshot.trace_id

    @property
    def request_id(self) -> str:
        return self.trace_snapshot.request_id

    @property
    def run_span_id(self) -> str:
        """返回 run span id；run 未启动时返回空字符串。"""
        if self.run_span is None:
            return ""
        return self.run_span.span_id

    def start_run_span(self) -> Span:
        """启动 spider 运行级 span，仅启动一次。"""
        if self.run_span is not None:
            return self.run_span

        span, tokens = start_span(
            service_name=self.service_name,
            stage="crawler.run",
            name=f"scrapy.run.{self.spider_name}",
            kind="internal",
            parent_span_id=self.parent_span_id or "",
            base_snapshot=self.trace_snapshot,
            bind_context=True,
            tags={
                "framework": "scrapy",
                "spider": self.spider_name,
                "target_site": self.target_site,
            },
        )
        self.run_span = span
        self.run_tokens = tokens
        return span

    async def finish_run_span(
        self,
        *,
        status: str = STATUS_OK,
        error_code: str = "",
        message: str = "",
        error_stack: str = "",
        extra_tags: Optional[dict[str, object]] = None,
    ) -> None:
        """结束 spider 运行级 span，并安全写入 backend。"""
        if self.run_span is None or self.run_finished:
            return

        self.run_finished = True
        finish_span(
            self.run_span,
            status=status,
            error_code=error_code,
            message=message,
            error_stack=error_stack,
            extra_tags=extra_tags,
        )
        reset_tokens(self.run_tokens)
        self.run_tokens = None
        await record_span_safe(self.backend, self.run_span)


def set_trace_session(crawler: object, session: ScrapyTraceSession) -> None:
    """将 tracing session 绑定到 crawler。"""
    setattr(crawler, TRACE_SESSION_ATTR, session)


def get_trace_session(spider: object) -> Optional[ScrapyTraceSession]:
    """从 spider.crawler 中取出 tracing session。"""
    crawler = getattr(spider, "crawler", None)
    if crawler is None:
        return None
    return getattr(crawler, TRACE_SESSION_ATTR, None)


def callback_name_from_request(request: Request) -> str:
    """提取 request 对应 callback 名；缺省为 parse。"""
    callback = request.callback
    if callback is None:
        return "parse"
    name = getattr(callback, "__name__", "")
    return name or "parse"


def target_site_from_request(request: Request, spider: object) -> str:
    """优先从 request.meta 获取 target_site，其次回退到 spider.target_site。"""
    target = request.meta.get("target_site")
    if target:
        return str(target)
    spider_target = getattr(spider, "target_site", "")
    return str(spider_target or "")


def extract_item_error(item: Any) -> tuple[str, str, str]:
    """从 item 中提取业务错误信息；仅支持 dict-like 对象。"""
    getter = getattr(item, "get", None)
    if not callable(getter):
        return "", "", ""
    error = getter("_error")
    stage = getter("_stage")
    error_code = getter("_error_code")
    return str(error or ""), str(stage or ""), str(error_code or "")


def build_item_error_message(item: Any) -> str:
    """将 item 中的错误字段格式化为可读消息。"""
    error, stage, _ = extract_item_error(item)
    if not error:
        return ""
    if stage:
        return f"[{stage}] {error}"
    return error


def build_item_error_code(item: Any, fallback: str = "upstream_request_error") -> str:
    """从 item 中提取错误码；未显式提供时使用通用上游错误码。"""
    error, _, error_code = extract_item_error(item)
    if not error:
        return ""
    return error_code or fallback


def request_tags(request: Request, spider: object, callback_name: str) -> dict[str, object]:
    """构造请求级 span 的标准 tags。"""
    parsed = urlsplit(request.url)
    return {
        "framework": "scrapy",
        "spider": getattr(spider, "name", ""),
        "target_site": target_site_from_request(request, spider),
        "callback": callback_name,
        "http.method": request.method,
        "http.host": parsed.netloc,
        "http.path": parsed.path or "/",
    }


class ScrapyTraceDownloaderMiddleware:
    """为下载阶段创建和结束请求级 span。"""

    def __init__(self, crawler: object = None) -> None:
        self._crawler = crawler

    @classmethod
    def from_crawler(cls, crawler: object) -> "ScrapyTraceDownloaderMiddleware":
        return cls(crawler=crawler)

    def _resolve_session(self, spider: object = None) -> Optional[ScrapyTraceSession]:
        session = get_trace_session(spider)
        if session is not None:
            return session
        return getattr(self._crawler, TRACE_SESSION_ATTR, None)

    def process_request(self, request: Request, spider: object = None) -> None:
        """请求发出前创建 outbound.http span。"""
        session = self._resolve_session(spider)
        if session is None:
            return None

        callback_name = callback_name_from_request(request)
        parent_span_id = str(request.meta.get(META_PARENT_SPAN_ID) or session.run_span_id)

        span, _ = start_span(
            service_name=session.service_name,
            stage="outbound.http",
            name=f"scrapy.request.{session.spider_name}.{callback_name}",
            kind="client",
            parent_span_id=parent_span_id,
            base_snapshot=session.trace_snapshot,
            tags=request_tags(request, spider, callback_name),
        )
        request.meta[META_REQUEST_SPAN] = span
        request.meta[META_REQUEST_SPAN_ID] = span.span_id
        return None

    def process_response(self, request: Request, response: Any, spider: object = None) -> Any:
        """响应返回后结束请求级 span。"""
        session = self._resolve_session(spider)
        span = request.meta.pop(META_REQUEST_SPAN, None)
        if session is None or span is None:
            return response

        status_code = getattr(response, "status", 0) or 0
        status = STATUS_ERROR if int(status_code) in ERROR_STATUS_CODES else STATUS_OK
        error_code = str(status_code) if status == STATUS_ERROR else ""
        message = f"HTTP {status_code}" if status == STATUS_ERROR else ""

        finish_span(
            span,
            status=status,
            error_code=error_code,
            message=message,
            extra_tags={
                "http.status_code": status_code,
                "proxy.enabled": "true" if request.meta.get("proxy") else "false",
            },
        )
        schedule_record_span(session.backend, span)
        return response

    def process_exception(self, request: Request, exception: Exception, spider: object = None) -> None:
        """请求阶段异常时结束请求级 span，并记录异常栈。"""
        session = self._resolve_session(spider)
        span = request.meta.pop(META_REQUEST_SPAN, None)
        if session is None or span is None:
            return None

        finish_span(
            span,
            status=STATUS_ERROR,
            error_code="crawler_execution_error",
            message=str(exception),
            error_stack=format_exception_stack(exception),
            extra_tags={"proxy.enabled": "true" if request.meta.get("proxy") else "false"},
        )
        schedule_record_span(session.backend, span)
        return None


class ScrapyTraceSpiderMiddleware:
    """为 callback 执行阶段创建和结束回调级 span。"""

    def __init__(self, crawler: object = None) -> None:
        self._crawler = crawler

    @classmethod
    def from_crawler(cls, crawler: object) -> "ScrapyTraceSpiderMiddleware":
        return cls(crawler=crawler)

    def _resolve_session(self, spider: object = None) -> Optional[ScrapyTraceSession]:
        session = get_trace_session(spider)
        if session is not None:
            return session
        return getattr(self._crawler, TRACE_SESSION_ATTR, None)

    def process_spider_input(self, response: Any, spider: object = None) -> None:
        """callback 执行前创建 crawler.callback span。"""
        session = self._resolve_session(spider)
        if session is None:
            return None

        request = response.request
        callback_name = callback_name_from_request(request)
        parent_span_id = str(request.meta.get(META_REQUEST_SPAN_ID) or session.run_span_id)

        span, tokens = start_span(
            service_name=session.service_name,
            stage="crawler.callback",
            name=f"scrapy.callback.{session.spider_name}.{callback_name}",
            kind="internal",
            parent_span_id=parent_span_id,
            base_snapshot=session.trace_snapshot,
            bind_context=True,
            tags={
                "framework": "scrapy",
                "spider": session.spider_name,
                "target_site": target_site_from_request(request, spider),
                "callback": callback_name,
            },
        )
        request.meta[META_CALLBACK_SCOPE] = CallbackScope(
            span=span,
            tokens=tokens,
            callback_name=callback_name,
        )
        return None

    def process_spider_output(
        self,
        response: Any,
        result: Iterable[Any],
        spider: object = None,
    ) -> Iterable[Any]:
        """包装 callback 输出，统计 item/request，并在结束时收尾 span。"""
        request = response.request
        scope = request.meta.get(META_CALLBACK_SCOPE)
        session = self._resolve_session(spider)
        if scope is None or session is None:
            return result
        return self._wrap_output(result, request, scope, session)

    async def process_spider_output_async(
        self,
        response: Any,
        result: AsyncIterator[Any],
        spider: object = None,
    ) -> AsyncIterator[Any]:
        """异步包装 callback 输出，兼容 async spider output。"""
        request = response.request
        scope = request.meta.get(META_CALLBACK_SCOPE)
        session = self._resolve_session(spider)
        if scope is None or session is None:
            async for value in result:
                yield value
            return

        async for value in self._wrap_output_async(result, request, scope, session):
            yield value

    def process_spider_exception(self, response: Any, exception: Exception, spider: object = None) -> None:
        """callback 抛异常时结束回调级 span。"""
        request = response.request
        scope = request.meta.get(META_CALLBACK_SCOPE)
        session = self._resolve_session(spider)
        if scope is None or session is None:
            return None

        self._finish_callback_scope(
            request,
            scope,
            session,
            status=STATUS_ERROR,
            error_code="crawler_execution_error",
            message=str(exception),
            error_stack=format_exception_stack(exception),
        )
        return None

    def _wrap_output(
        self,
        result: Iterable[Any],
        request: Request,
        scope: CallbackScope,
        session: ScrapyTraceSession,
    ) -> Iterator[Any]:
        """遍历 callback 输出，建立父子链路并汇总执行结果。"""
        item_count = 0
        request_count = 0
        status = STATUS_OK
        error_code = ""
        message = ""
        error_stack = ""

        try:
            for value in result:
                if isinstance(value, Request):
                    # 子请求默认挂到当前 callback span 之下
                    value.meta.setdefault(META_PARENT_SPAN_ID, scope.span.span_id)
                    request_count += 1
                else:
                    item_count += 1
                    item_error_message = build_item_error_message(value)
                    if item_error_message and status != STATUS_ERROR:
                        # item 带业务错误时，将当前 callback 标记为失败
                        status = STATUS_ERROR
                        error_code = build_item_error_code(value)
                        message = item_error_message
                yield value
        except Exception as exc:
            status = STATUS_ERROR
            error_code = "crawler_execution_error"
            message = str(exc)
            error_stack = format_exception_stack(exc)
            raise
        finally:
            self._finish_callback_scope(
                request,
                scope,
                session,
                status=status,
                error_code=error_code,
                message=message,
                error_stack=error_stack,
                extra_tags={
                    "result.item_count": item_count,
                    "result.request_count": request_count,
                },
            )

    async def _wrap_output_async(
        self,
        result: AsyncIterator[Any],
        request: Request,
        scope: CallbackScope,
        session: ScrapyTraceSession,
    ) -> AsyncIterator[Any]:
        """遍历异步 callback 输出，建立父子链路并汇总执行结果。"""
        item_count = 0
        request_count = 0
        status = STATUS_OK
        error_code = ""
        message = ""
        error_stack = ""

        try:
            async for value in result:
                if isinstance(value, Request):
                    # 子请求默认挂到当前 callback span 之下
                    value.meta.setdefault(META_PARENT_SPAN_ID, scope.span.span_id)
                    request_count += 1
                else:
                    item_count += 1
                    item_error_message = build_item_error_message(value)
                    if item_error_message and status != STATUS_ERROR:
                        # item 带业务错误时，将当前 callback 标记为失败
                        status = STATUS_ERROR
                        error_code = build_item_error_code(value)
                        message = item_error_message
                yield value
        except Exception as exc:
            status = STATUS_ERROR
            error_code = "crawler_execution_error"
            message = str(exc)
            error_stack = format_exception_stack(exc)
            raise
        finally:
            self._finish_callback_scope(
                request,
                scope,
                session,
                status=status,
                error_code=error_code,
                message=message,
                error_stack=error_stack,
                extra_tags={
                    "result.item_count": item_count,
                    "result.request_count": request_count,
                },
            )

    def _finish_callback_scope(
        self,
        request: Request,
        scope: CallbackScope,
        session: ScrapyTraceSession,
        *,
        status: str,
        error_code: str,
        message: str,
        error_stack: str = "",
        extra_tags: Optional[dict[str, object]] = None,
    ) -> None:
        """结束 callback span；保证只执行一次。"""
        if scope.finished:
            return

        scope.finished = True
        finish_span(
            scope.span,
            status=status,
            error_code=error_code,
            message=message,
            error_stack=error_stack,
            extra_tags=extra_tags,
        )
        reset_tokens(scope.tokens)
        request.meta.pop(META_CALLBACK_SCOPE, None)
        schedule_record_span(session.backend, scope.span)
