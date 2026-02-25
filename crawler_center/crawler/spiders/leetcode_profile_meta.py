"""LeetCode 用户主页元信息抓取 spider。

抓取目标：
- 访问 ``/u/{username}/`` 用户主页。
- 解析页面中的基础元信息（如 ``og:title``、``og:description``）。

产出约定：
- 成功时产出 parser 生成的单条元信息 dict。
- 失败与不存在场景由 parser 侧统一编码为稳定字段结构。
"""

from __future__ import annotations

from typing import Any

import scrapy

from crawler_center.crawler.parsers.leetcode_parser import parse_profile_meta_html
from crawler_center.crawler.spiders.leetcode_common import LeetCodeSpiderBase


class LeetCodeProfileMetaSpider(LeetCodeSpiderBase):
    """抓取 LeetCode 主页存在性与 OpenGraph 元信息。"""

    name = "leetcode_profile_meta"

    def __init__(self, base_url: str, username: str, sleep_sec: float = 0.0, **kwargs: Any) -> None:
        """初始化抓取参数（委托给基类完成归一化）。"""
        super().__init__(base_url=base_url, username=username, sleep_sec=sleep_sec, **kwargs)

    def start_requests(self):
        """发起主页请求。

        说明：
        - ``dont_filter=True`` 避免同 URL 被去重，确保每次调用都实际访问。
        - ``target_site`` 元数据用于代理中间件按站点回传健康状态。
        """
        yield scrapy.Request(
            url=self.profile_url(),
            callback=self.parse_profile,
            dont_filter=True,
            meta={"target_site": self.target_site},
        )

    def parse_profile(self, response: scrapy.http.Response):
        """解析主页 HTML 并产出标准化元信息。"""
        yield parse_profile_meta_html(
            page_html=response.text,
            status_code=response.status,
            final_url=response.url,
        )
