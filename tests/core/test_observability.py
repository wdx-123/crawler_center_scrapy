from __future__ import annotations

import asyncio
import copy

import pytest
import scrapy

from crawler_center.crawler.runner import ScrapyRunnerService
from crawler_center.observability.context import reset_trace_context, set_trace_context
from crawler_center.services.proxy_service import ProxyService
from tests.conftest import build_test_settings


class StubTraceBackend:
    def __init__(self) -> None:
        self.spans = []

    async def record_span(self, span) -> None:
        self.spans.append(copy.deepcopy(span))

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class ChainedLocalFileSpider(scrapy.Spider):
    name = "chained_local_file_spider"
    target_site = "local"

    def __init__(self, first_url: str, second_url: str, **kwargs):
        super().__init__(**kwargs)
        self.first_url = first_url
        self.second_url = second_url

    async def start(self):
        yield scrapy.Request(
            self.first_url,
            callback=self.parse_first,
            dont_filter=True,
            meta={"target_site": self.target_site, "use_proxy": False},
        )

    def parse_first(self, response):
        yield {"page": "first"}
        yield scrapy.Request(
            self.second_url,
            callback=self.parse_second,
            dont_filter=True,
            meta={"target_site": self.target_site, "use_proxy": False},
        )

    def parse_second(self, response):
        yield {"page": "second"}


class ErrorItemSpider(scrapy.Spider):
    name = "error_item_spider"
    target_site = "local"

    def __init__(self, file_url: str, error_code: str = "", **kwargs):
        super().__init__(**kwargs)
        self.file_url = file_url
        self.error_code = error_code

    async def start(self):
        yield scrapy.Request(
            self.file_url,
            callback=self.parse_failure,
            dont_filter=True,
            meta={"target_site": self.target_site, "use_proxy": False},
        )

    def parse_failure(self, response):
        item = {"_error": "boom", "_stage": "parse_failure"}
        if self.error_code:
            item["_error_code"] = self.error_code
        yield item


class AsyncOutputSpider(scrapy.Spider):
    name = "async_output_spider"
    target_site = "local"

    def __init__(self, file_url: str, **kwargs):
        super().__init__(**kwargs)
        self.file_url = file_url

    async def start(self):
        yield scrapy.Request(
            self.file_url,
            callback=self.parse_async,
            dont_filter=True,
            meta={"target_site": self.target_site, "use_proxy": False},
        )

    async def parse_async(self, response):
        yield {"page": "async-first"}
        await asyncio.sleep(0)
        yield {"page": "async-second"}


def set_parent_trace():
    return set_trace_context(
        trace_id="fedcba98765432100123456789abcdef",
        span_id="2222222222222222",
        parent_span_id="",
        request_id="req-test-observability",
    )


def build_runner_with_backend():
    settings = build_test_settings()
    proxy_service = ProxyService(probe_urls=settings.probe_urls, user_agent=settings.default_user_agent)
    backend = StubTraceBackend()
    ScrapyRunnerService.reset_instance_for_tests()
    runner = ScrapyRunnerService.get_instance(app_settings=settings, proxy_service=proxy_service)
    runner.set_trace_backend(backend)
    return runner, backend


@pytest.mark.asyncio
async def test_scrapy_trace_records_full_chain(tmp_path):
    first_file = tmp_path / "first.html"
    second_file = tmp_path / "second.html"
    first_file.write_text("<html><body>first</body></html>", encoding="utf-8")
    second_file.write_text("<html><body>second</body></html>", encoding="utf-8")

    runner, backend = build_runner_with_backend()
    tokens = set_parent_trace()
    try:
        items = await runner.run(
            ChainedLocalFileSpider,
            first_url=first_file.resolve().as_uri(),
            second_url=second_file.resolve().as_uri(),
            run_timeout_sec=3,
        )
    finally:
        reset_trace_context(tokens)

    await asyncio.sleep(0.05)

    assert items == [{"page": "first"}, {"page": "second"}]
    assert len(backend.spans) == 5

    run_span = next(span for span in backend.spans if span.stage == "crawler.run")
    first_request_span = next(
        span for span in backend.spans if span.stage == "outbound.http" and span.name.endswith(".parse_first")
    )
    second_request_span = next(
        span for span in backend.spans if span.stage == "outbound.http" and span.name.endswith(".parse_second")
    )
    first_callback_span = next(
        span for span in backend.spans if span.stage == "crawler.callback" and span.name.endswith(".parse_first")
    )
    second_callback_span = next(
        span for span in backend.spans if span.stage == "crawler.callback" and span.name.endswith(".parse_second")
    )

    assert run_span.parent_span_id == "2222222222222222"
    assert first_request_span.parent_span_id == run_span.span_id
    assert first_callback_span.parent_span_id == first_request_span.span_id
    assert second_request_span.parent_span_id == first_callback_span.span_id
    assert second_callback_span.parent_span_id == second_request_span.span_id
    assert all(span.status == "ok" for span in backend.spans)


@pytest.mark.asyncio
async def test_scrapy_trace_supports_async_output_without_deprecation_warning(tmp_path, caplog):
    html_file = tmp_path / "async.html"
    html_file.write_text("<html><body>async</body></html>", encoding="utf-8")

    runner, backend = build_runner_with_backend()
    tokens = set_parent_trace()
    caplog.clear()
    try:
        with caplog.at_level("WARNING", logger="scrapy.core.spidermw"):
            items = await runner.run(
                AsyncOutputSpider,
                file_url=html_file.resolve().as_uri(),
                run_timeout_sec=3,
            )
    finally:
        reset_trace_context(tokens)

    await asyncio.sleep(0.05)

    assert items == [{"page": "async-first"}, {"page": "async-second"}]
    warning_messages = [record.getMessage() for record in caplog.records if record.name == "scrapy.core.spidermw"]
    assert not any("doesn't support asynchronous spider output" in message for message in warning_messages)

    callback_span = next(span for span in backend.spans if span.stage == "crawler.callback")
    assert callback_span.status == "ok"


@pytest.mark.asyncio
async def test_scrapy_trace_marks_error_items(tmp_path):
    html_file = tmp_path / "error.html"
    html_file.write_text("<html><body>error</body></html>", encoding="utf-8")

    runner, backend = build_runner_with_backend()
    tokens = set_parent_trace()
    try:
        items = await runner.run(
            ErrorItemSpider,
            file_url=html_file.resolve().as_uri(),
            run_timeout_sec=3,
        )
    finally:
        reset_trace_context(tokens)

    await asyncio.sleep(0.05)

    assert items == [{"_error": "boom", "_stage": "parse_failure"}]
    callback_span = next(span for span in backend.spans if span.stage == "crawler.callback")
    run_span = next(span for span in backend.spans if span.stage == "crawler.run")

    assert callback_span.status == "error"
    assert callback_span.error_code == "upstream_request_error"
    assert "boom" in callback_span.message
    assert run_span.status == "error"
    assert run_span.error_code == "upstream_request_error"
    assert "boom" in run_span.message


@pytest.mark.asyncio
async def test_scrapy_trace_uses_item_specific_error_code(tmp_path):
    html_file = tmp_path / "error-auth.html"
    html_file.write_text("<html><body>error</body></html>", encoding="utf-8")

    runner, backend = build_runner_with_backend()
    tokens = set_parent_trace()
    try:
        items = await runner.run(
            ErrorItemSpider,
            file_url=html_file.resolve().as_uri(),
            error_code="upstream_auth_failed",
            run_timeout_sec=3,
        )
    finally:
        reset_trace_context(tokens)

    await asyncio.sleep(0.05)

    assert items == [{"_error": "boom", "_stage": "parse_failure", "_error_code": "upstream_auth_failed"}]
    callback_span = next(span for span in backend.spans if span.stage == "crawler.callback")
    run_span = next(span for span in backend.spans if span.stage == "crawler.run")

    assert callback_span.status == "error"
    assert callback_span.error_code == "upstream_auth_failed"
    assert run_span.status == "error"
    assert run_span.error_code == "upstream_auth_failed"
