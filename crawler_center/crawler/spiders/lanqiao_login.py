"""Lanqiao 登录 spider（占位实现）。

说明：
- 当前项目尚未落地蓝桥登录流程，此 spider 用于保留接口形态与执行链路。
- 统一返回 ``_error``，让 service/router 能稳定映射为 501 或上游错误语义。
"""

from __future__ import annotations

from typing import Any

import scrapy

from crawler_center.services.proxy_service import TargetSite


class LanqiaoLoginSpider(scrapy.Spider):
    """蓝桥登录占位 spider，便于后续无缝替换为真实实现。"""

    name = "lanqiao_login"
    target_site = TargetSite.LANQIAO.value

    def __init__(self, base_url: str, username: str, password: str, **kwargs: Any) -> None:
        """保存登录参数（当前未实际发起登录表单请求）。"""
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password

    def start_requests(self):
        """占位流程：仅请求首页验证网络连通性。"""
        yield scrapy.Request(
            url=f"{self.base_url}/",
            callback=self.parse_placeholder,
            dont_filter=True,
            meta={"target_site": self.target_site},
        )

    def parse_placeholder(self, response: scrapy.http.Response):
        """固定返回未实现错误，保持上层错误处理路径稳定。"""
        yield {"_error": "Lanqiao login not implemented"}
