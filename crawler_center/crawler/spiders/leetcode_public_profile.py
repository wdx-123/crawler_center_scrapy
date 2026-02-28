"""LeetCode 公开资料抓取 spider。

抓取目标：
- 调用 GraphQL ``userPublicProfile`` 获取用户公开展示字段。

字段范围（由 parser 统一归一化）：
- userSlug
- realName
- userAvatar
"""

from __future__ import annotations

from typing import Any

import scrapy

from crawler_center.crawler.parsers.leetcode_parser import parse_graphql_payload, parse_public_profile_data
from crawler_center.crawler.spiders.leetcode_common import LeetCodeSpiderBase


class LeetCodePublicProfileSpider(LeetCodeSpiderBase):
    """抓取 LeetCode 用户公开资料。"""

    name = "leetcode_public_profile"

    QUERY = """
    query userPublicProfile($userSlug: String!) {
      userProfilePublicProfile(userSlug: $userSlug) {
        profile {
          userSlug
          realName
          userAvatar
        }
      }
    }
    """

    def __init__(self, base_url: str, username: str, sleep_sec: float = 0.0, **kwargs: Any) -> None:
        """初始化抓取参数。"""
        super().__init__(base_url=base_url, username=username, sleep_sec=sleep_sec, **kwargs)

    async def start(self):
        """兼容 Scrapy 2.13+ 的异步入口，复用既有请求构造逻辑。"""
        for request in self.start_requests():
            yield request

    def start_requests(self):
        """先请求根页面，获取 cookie/csrf 上下文。"""
        yield scrapy.Request(
            url=self.root_url(),
            callback=self.parse_root,
            dont_filter=True,
            meta={"target_site": self.target_site},
        )

    def parse_root(self, response: scrapy.http.Response):
        """提取 csrf 并发起公开资料查询。"""
        csrf_token = self.extract_csrf_from_response(response)
        yield self.build_graphql_request(
            url=self.graphql_url(),
            operation_name="userPublicProfile",
            query=self.QUERY,
            variables={"userSlug": self.username},
            referer=self.profile_url(),
            csrf_token=csrf_token,
            callback=self.parse_graphql,
        )

    def parse_graphql(self, response: scrapy.http.Response):
        """解析 GraphQL 响应并产出公开资料 dict。"""
        if response.status >= 400:
            yield {"_error": f"GraphQL HTTP {response.status}", "_status": response.status}
            return

        try:
            payload = response.json()
        except Exception:
            yield {"_error": "GraphQL response is not valid JSON"}
            return

        parsed = parse_graphql_payload(payload)
        if "_error" in parsed:
            yield parsed
            return

        yield parse_public_profile_data(parsed)
