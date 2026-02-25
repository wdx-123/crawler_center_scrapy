from __future__ import annotations

import pytest
import scrapy
from twisted.internet.defer import Deferred

from crawler_center.core.errors import CrawlerTimeoutError
from crawler_center.crawler.runner import ScrapyRunnerService
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

    ScrapyRunnerService.reset_instance_for_tests()
    runner = ScrapyRunnerService.get_instance(app_settings=settings, proxy_service=proxy_service)

    def never_finishes(*args, **kwargs):
        return Deferred()

    monkeypatch.setattr(runner._runner, "crawl", never_finishes)

    with pytest.raises(CrawlerTimeoutError):
        await runner.run(DummySpider, run_timeout_sec=0.01)
