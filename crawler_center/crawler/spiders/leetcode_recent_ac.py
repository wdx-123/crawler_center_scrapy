"""LeetCode 最近 AC 记录抓取 spider。

抓取流程：
1) 先访问站点根路径，获取 cookie / csrf 上下文。
2) 再调用 GraphQL ``recentACSubmissions`` 查询。
3) 将响应交给 parser 清洗为统一 item 列表。

错误约定：
- 网络/HTTP/JSON/GraphQL 错误统一产出 ``_error`` 字段，由 service 层升级为业务异常。
"""

from __future__ import annotations

from typing import Any

import scrapy

from crawler_center.crawler.parsers.leetcode_parser import parse_graphql_payload, parse_recent_ac_data
from crawler_center.crawler.spiders.leetcode_common import LeetCodeSpiderBase


class LeetCodeRecentAcSpider(LeetCodeSpiderBase):
    """抓取用户最近通过题目记录。"""

    name = "leetcode_recent_ac"

    QUERY = """
    query recentACSubmissions($userSlug: String!) {
      recentACSubmissions(userSlug: $userSlug) {
        submitTime
        question {
          title
          translatedTitle
          titleSlug
          questionFrontendId
        }
      }
    }
    """

    def __init__(self, base_url: str, username: str, sleep_sec: float = 0.0, **kwargs: Any) -> None:
        """初始化抓取参数。"""
        super().__init__(base_url=base_url, username=username, sleep_sec=sleep_sec, **kwargs)

    def start_requests(self):
        """先请求根页面，建立 GraphQL 请求所需上下文。"""
        yield scrapy.Request(
            url=self.root_url(),
            callback=self.parse_root,
            dont_filter=True,
            meta={"target_site": self.target_site},
        )

    def parse_root(self, response: scrapy.http.Response):
        """提取 csrf 并发起 GraphQL 请求。"""
        csrf_token = self.extract_csrf_from_response(response)
        yield self.build_graphql_request(
            url=self.graphql_noj_url(),
            operation_name="recentACSubmissions",
            query=self.QUERY,
            variables={"userSlug": self.username},
            referer=self.profile_url(),
            csrf_token=csrf_token,
            callback=self.parse_graphql,
        )

    def parse_graphql(self, response: scrapy.http.Response):
        """解析 GraphQL 响应并输出记录。

        产出：
        - 正常时：多条 ``{title, slug, timestamp}``。
        - 异常时：单条 ``{"_error": "...", "_status": ...}``。
        """
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

        for row in parse_recent_ac_data(parsed):
            yield row
