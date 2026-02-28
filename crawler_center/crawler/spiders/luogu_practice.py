"""Luogu 练题数据抓取 spider。

站点特性：
- 同一接口可能返回 HTML（含 ``lentille-context``）或 JSON。
- 404 代表用户不存在/不可见，按业务约定返回空结构而非报错。

错误约定：
- HTTP >= 400（除 404）或解析失败时，产出 ``_error`` item 供 service 层抛出异常。
"""

from __future__ import annotations

import json
from typing import Any, Dict

import scrapy

from crawler_center.crawler.parsers.luogu_parser import extract_lentille_context, parse_luogu_practice_context
from crawler_center.services.proxy_service import TargetSite


class LuoguPracticeSpider(scrapy.Spider):
    """抓取 Luogu 用户通过题目列表及数量。"""

    name = "luogu_practice"
    target_site = TargetSite.LUOGU.value

    def __init__(self, base_url: str, uid: int, sleep_sec: float = 0.0, **kwargs: Any) -> None:
        """初始化抓取参数。"""
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")
        self.uid = int(uid)
        self.sleep_sec = sleep_sec

    def practice_url(self) -> str:
        """返回用户练题页 URL。"""
        return f"{self.base_url}/user/{self.uid}/practice"

    def start_requests(self):
        """发起练题页请求。

        ``x-lentille-request: content-only`` 用于提升拿到结构化上下文的概率。
        """
        yield scrapy.Request(
            url=self.practice_url(),
            callback=self.parse_practice,
            headers={"x-lentille-request": "content-only"},
            dont_filter=True,
            meta={"target_site": self.target_site},
        )

    async def start(self):
        """兼容 Scrapy 2.13+ 的异步入口，复用既有请求构造逻辑。"""
        for request in self.start_requests():
            yield request

    def parse_practice(self, response: scrapy.http.Response):
        """解析 Luogu 响应为统一结构。

        产出：
        - 用户不存在/无数据：``{"user": None, "passed": [], "passed_count": 0}``
        - 上游错误：``{"_error": "...", "_status": ...}``
        - 正常数据：parser 归一化后的用户做题信息。
        """
        if response.status == 404:
            yield {"user": None, "passed": [], "passed_count": 0}
            return

        if response.status >= 400:
            yield {"_error": f"Luogu HTTP {response.status}", "_status": response.status}
            return

        content_type = (response.headers.get("Content-Type") or b"").decode("utf-8", errors="ignore").lower()
        context: Dict[str, Any] = {}

        if "application/json" in content_type:
            try:
                context = response.json()
            except Exception:
                yield {"_error": "Luogu JSON decode failed"}
                return
        else:
            try:
                context = extract_lentille_context(response.text)
            except json.JSONDecodeError:
                yield {"_error": "Luogu lentille-context decode failed"}
                return

        if not context:
            yield {"user": None, "passed": [], "passed_count": 0}
            return

        yield parse_luogu_practice_context(context)
