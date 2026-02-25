"""LeetCode 提交统计抓取 spider。

抓取流程：
1) 访问根页面拿 cookie/csrf。
2) 调用 GraphQL ``userQuestionProgress`` 查询统计数据。
3) 由 parser 输出稳定 dict 结构。

错误约定：
- 任何可恢复抓取错误都通过 ``_error`` item 上报，交由 service 层统一处理。
"""

from __future__ import annotations

from typing import Any

import scrapy

from crawler_center.crawler.parsers.leetcode_parser import parse_graphql_payload, parse_submit_stats_data
from crawler_center.crawler.spiders.leetcode_common import LeetCodeSpiderBase


class LeetCodeSubmitStatsSpider(LeetCodeSpiderBase):
    """抓取用户题目提交与通过统计。"""

    name = "leetcode_submit_stats"

    QUERY = """
    query userQuestionProgress($userSlug: String!) {
      userProfileUserQuestionSubmitStats(userSlug: $userSlug) {
        acSubmissionNum { difficulty count }
        totalSubmissionNum { difficulty count }
      }
      userProfileUserQuestionProgress(userSlug: $userSlug) {
        numAcceptedQuestions { difficulty count }
        numFailedQuestions { difficulty count }
        numUntouchedQuestions { difficulty count }
      }
    }
    """

    def __init__(self, base_url: str, username: str, sleep_sec: float = 0.0, **kwargs: Any) -> None:
        """初始化抓取参数。"""
        super().__init__(base_url=base_url, username=username, sleep_sec=sleep_sec, **kwargs)

    def start_requests(self):
        """先获取站点上下文，再进入 GraphQL 查询。"""
        yield scrapy.Request(
            url=self.root_url(),
            callback=self.parse_root,
            dont_filter=True,
            meta={"target_site": self.target_site},
        )

    def parse_root(self, response: scrapy.http.Response):
        """提取 csrf 后发起统计查询。"""
        csrf_token = self.extract_csrf_from_response(response)
        yield self.build_graphql_request(
            url=self.graphql_url(),
            operation_name="userQuestionProgress",
            query=self.QUERY,
            variables={"userSlug": self.username},
            referer=self.profile_url(),
            csrf_token=csrf_token,
            callback=self.parse_graphql,
        )

    def parse_graphql(self, response: scrapy.http.Response):
        """解析 GraphQL 响应并产出统计结果。"""
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

        yield parse_submit_stats_data(parsed)
