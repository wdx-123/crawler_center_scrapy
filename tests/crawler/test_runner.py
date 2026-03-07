from __future__ import annotations

import asyncio
import copy

import pytest
import scrapy
from twisted.internet.defer import Deferred

from crawler_center.core.errors import CrawlerExecutionError, CrawlerTimeoutError
from crawler_center.crawler.runner import ScrapyRunnerService
from crawler_center.observability.context import reset_trace_context, set_trace_context
from crawler_center.services.proxy_service import ProxyService
from tests.conftest import build_test_settings


class LocalFileSpider(scrapy.Spider):
    name = "local_file_spider"

    def __init__(self, file_url: str, **kwargs):
        super().__init__(**kwargs)
        self.file_url = file_url

    async def start(self):
        yield scrapy.Request(
            self.file_url,
            callback=self.parse,
            dont_filter=True,
            meta={"target_site": "leetcode", "use_proxy": False},
        )

    def parse(self, response):
        title = response.xpath("//title/text()").get(default="")
        yield {"title": title}


class DummySpider(scrapy.Spider):
    name = "dummy_spider"


class StubTraceBackend:
    def __init__(self) -> None:
        self.spans = []

    async def record_span(self, span) -> None:
        self.spans.append(copy.deepcopy(span))

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


def set_parent_trace():
    return set_trace_context(
        trace_id="0123456789abcdef0123456789abcdef",
        span_id="1111111111111111",
        parent_span_id="",
        request_id="req-test-runner",
    )


@pytest.mark.asyncio
async def test_runner_collects_items(tmp_path):
    html_file = tmp_path / "sample.html"
    html_file.write_text("<html><head><title>ok</title></head><body></body></html>", encoding="utf-8")

    settings = build_test_settings()
    proxy_service = ProxyService(probe_urls=settings.probe_urls, user_agent=settings.default_user_agent)

    ScrapyRunnerService.reset_instance_for_tests()
    runner = ScrapyRunnerService.get_instance(app_settings=settings, proxy_service=proxy_service)

    items = await runner.run(LocalFileSpider, file_url=html_file.resolve().as_uri(), run_timeout_sec=3)

    assert items == [{"title": "ok"}]


@pytest.mark.asyncio
async def test_runner_timeout(monkeypatch):
    settings = build_test_settings()
    proxy_service = ProxyService(probe_urls=settings.probe_urls, user_agent=settings.default_user_agent)
    backend = StubTraceBackend()

    ScrapyRunnerService.reset_instance_for_tests()
    runner = ScrapyRunnerService.get_instance(app_settings=settings, proxy_service=proxy_service)
    runner.set_trace_backend(backend)

    def never_finishes(*args, **kwargs):
        return Deferred()

    monkeypatch.setattr(runner._runner, "crawl", never_finishes)

    tokens = set_parent_trace()
    try:
        with pytest.raises(CrawlerTimeoutError):
            await runner.run(DummySpider, run_timeout_sec=0.01)
    finally:
        reset_trace_context(tokens)

    assert len(backend.spans) == 1
    span = backend.spans[0]
    assert span.stage == "crawler.run"
    assert span.status == "error"
    assert span.error_code == "crawler_timeout"


@pytest.mark.asyncio
async def test_runner_rebinds_reactor_loop(tmp_path):
    html_file = tmp_path / "sample.html"
    html_file.write_text("<html><head><title>ok</title></head><body></body></html>", encoding="utf-8")

    settings = build_test_settings()
    proxy_service = ProxyService(probe_urls=settings.probe_urls, user_agent=settings.default_user_agent)

    ScrapyRunnerService.reset_instance_for_tests()
    runner = ScrapyRunnerService.get_instance(app_settings=settings, proxy_service=proxy_service)

    from twisted.internet import reactor

    if not hasattr(reactor, "_asyncioEventloop"):
        pytest.skip("reactor has no asyncio loop binding")

    stale_loop = asyncio.new_event_loop()
    try:
        reactor._asyncioEventloop = stale_loop  # type: ignore[attr-defined]
        items = await runner.run(LocalFileSpider, file_url=html_file.resolve().as_uri(), run_timeout_sec=3)
    finally:
        stale_loop.close()

    assert items == [{"title": "ok"}]
    assert reactor._asyncioEventloop is asyncio.get_running_loop()  # type: ignore[attr-defined]

# 下面这个测试是为了验证当 reactor 不是 AsyncioSelectorReactor 时，
# runner 能否抛出带有明确提示信息的异常，指导用户去调整 Windows 开发环境的 asyncio policy 设置。
@pytest.mark.asyncio
async def test_runner_reactor_mismatch_has_actionable_message(monkeypatch):
    settings = build_test_settings()
    proxy_service = ProxyService(probe_urls=settings.probe_urls, user_agent=settings.default_user_agent)

    ScrapyRunnerService.reset_instance_for_tests()
    runner = ScrapyRunnerService.get_instance(app_settings=settings, proxy_service=proxy_service)

    monkeypatch.setattr("crawler_center.crawler.runner._is_asyncio_selector_reactor", lambda: False)

    with pytest.raises(CrawlerExecutionError) as exc:
        await runner.run(DummySpider, run_timeout_sec=0.01)

    message = str(exc.value)
    assert "AsyncioSelectorReactor" in message
    assert "crawler_center.api.run" in message


@pytest.mark.asyncio
async def test_runner_loop_without_add_reader_has_actionable_message(monkeypatch):
    settings = build_test_settings()
    proxy_service = ProxyService(probe_urls=settings.probe_urls, user_agent=settings.default_user_agent)

    ScrapyRunnerService.reset_instance_for_tests()
    runner = ScrapyRunnerService.get_instance(app_settings=settings, proxy_service=proxy_service)

    monkeypatch.setattr("crawler_center.crawler.runner._is_asyncio_selector_reactor", lambda: True)
    monkeypatch.setattr("crawler_center.crawler.runner._loop_supports_add_reader", lambda _loop: False)

    with pytest.raises(CrawlerExecutionError) as exc:
        await runner.run(DummySpider, run_timeout_sec=0.01)

    message = str(exc.value)
    assert "crawler_center.api.run" in message
    assert "current_event_loop" in message


@pytest.mark.asyncio
async def test_runner_execution_error_records_run_span(monkeypatch):
    settings = build_test_settings()
    proxy_service = ProxyService(probe_urls=settings.probe_urls, user_agent=settings.default_user_agent)
    backend = StubTraceBackend()

    ScrapyRunnerService.reset_instance_for_tests()
    runner = ScrapyRunnerService.get_instance(app_settings=settings, proxy_service=proxy_service)
    runner.set_trace_backend(backend)

    def raise_execution_error(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(runner._runner, "crawl", raise_execution_error)

    tokens = set_parent_trace()
    try:
        with pytest.raises(CrawlerExecutionError) as exc:
            await runner.run(DummySpider, run_timeout_sec=0.01)
    finally:
        reset_trace_context(tokens)

    assert "boom" in str(exc.value)
    assert len(backend.spans) == 1
    span = backend.spans[0]
    assert span.stage == "crawler.run"
    assert span.status == "error"
    assert span.error_code == "crawler_execution_error"
