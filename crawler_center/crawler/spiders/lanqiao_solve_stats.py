"""Lanqiao 做题统计 spider（占位实现）。

说明：
- 当前仅保留参数/请求框架，便于后续补齐真实抓取逻辑。
- 若传入 cookie，会在请求头附带 ``Cookie``，保持未来实现兼容。
- 统一返回 ``_error``，由 service/router 映射为稳定错误响应。
"""

from __future__ import annotations

from typing import Any, Optional

import scrapy

from crawler_center.services.proxy_service import TargetSite


class LanqiaoSolveStatsSpider(scrapy.Spider):
    """蓝桥做题统计占位 spider。"""

    name = "lanqiao_solve_stats"
    target_site = TargetSite.LANQIAO.value

    def __init__(self, base_url: str, cookie_header: Optional[str] = None, user_id: Optional[str] = None, **kwargs: Any) -> None:
        """保存查询参数（cookie_header/user_id 供后续真实实现使用）。"""
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")
        self.cookie_header = cookie_header
        self.user_id = user_id

    def start_requests(self):
        """占位流程：请求首页并可选携带 Cookie。"""
        headers = {}
        if self.cookie_header:
            headers["Cookie"] = self.cookie_header

        yield scrapy.Request(
            url=f"{self.base_url}/",
            callback=self.parse_placeholder,
            headers=headers,
            dont_filter=True,
            meta={"target_site": self.target_site},
        )

    def parse_placeholder(self, response: scrapy.http.Response):
        """固定返回未实现错误，保证上层行为可预测。"""
        yield {"_error": "Lanqiao solve_stats not implemented"}
