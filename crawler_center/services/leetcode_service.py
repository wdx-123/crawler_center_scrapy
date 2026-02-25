"""LeetCode 业务服务实现。

该服务负责将多个 spider 的抓取结果转换为稳定的 API 数据结构，
并在发现上游错误标记时升级为统一业务异常。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from crawler_center.core.config import AppSettings
from crawler_center.core.errors import UpstreamRequestError
from crawler_center.crawler.runner import ScrapyRunnerService
from crawler_center.crawler.spiders.leetcode_profile_meta import LeetCodeProfileMetaSpider
from crawler_center.crawler.spiders.leetcode_public_profile import LeetCodePublicProfileSpider
from crawler_center.crawler.spiders.leetcode_recent_ac import LeetCodeRecentAcSpider
from crawler_center.crawler.spiders.leetcode_submit_stats import LeetCodeSubmitStatsSpider


class LeetCodeService:
    """LeetCode 抓取能力聚合服务。"""

    def __init__(self, runner: ScrapyRunnerService, settings: AppSettings) -> None:
        self._runner = runner
        self._settings = settings

    async def profile_meta(self, username: str, sleep_sec: float) -> Dict[str, Any]:
        """抓取用户主页元信息。"""
        items = await self._runner.run(
            LeetCodeProfileMetaSpider,
            base_url=self._settings.leetcode_base_url,
            username=username,
            sleep_sec=sleep_sec,
        )
        self._raise_if_item_error(items, "leetcode profile_meta")
        if not items:
            return {"exists": False, "reason": "empty result", "url_final": ""}
        return dict(items[0])

    async def recent_ac(self, username: str, sleep_sec: float) -> List[Dict[str, Any]]:
        """抓取最近 AC 记录并补充本地格式化时间。"""
        items = await self._runner.run(
            LeetCodeRecentAcSpider,
            base_url=self._settings.leetcode_base_url,
            username=username,
            sleep_sec=sleep_sec,
        )
        self._raise_if_item_error(items, "leetcode recent_ac")

        out: List[Dict[str, Any]] = []
        for row in items:
            timestamp = int(row.get("timestamp", 0))
            out.append(
                {
                    "title": row.get("title", ""),
                    "slug": row.get("slug", ""),
                    "timestamp": timestamp,
                    "time": format_local_time(timestamp) if timestamp else "",
                }
            )
        return out

    async def submit_stats(self, username: str, sleep_sec: float) -> Dict[str, Any]:
        """抓取用户提交统计。"""
        items = await self._runner.run(
            LeetCodeSubmitStatsSpider,
            base_url=self._settings.leetcode_base_url,
            username=username,
            sleep_sec=sleep_sec,
        )
        self._raise_if_item_error(items, "leetcode submit_stats")
        if not items:
            return {}
        return dict(items[0])

    async def public_profile(self, username: str, sleep_sec: float) -> Dict[str, Any]:
        """抓取用户公开资料。"""
        items = await self._runner.run(
            LeetCodePublicProfileSpider,
            base_url=self._settings.leetcode_base_url,
            username=username,
            sleep_sec=sleep_sec,
        )
        self._raise_if_item_error(items, "leetcode public_profile")
        if not items:
            return {"userSlug": "", "realName": "", "userAvatar": ""}
        return dict(items[0])

    async def crawl(self, username: str, sleep_sec: float) -> Dict[str, Any]:
        """聚合抓取 meta/recent_ac/stats。

        当主页不存在时，直接返回空结果，避免无意义的下游请求。
        """
        meta = await self.profile_meta(username=username, sleep_sec=sleep_sec)
        if not meta.get("exists"):
            return {"meta": meta, "recent_accepted": [], "stats": None}

        # recent_ac 与 submit_stats 相互独立，可并发执行降低总耗时。
        recent_task = asyncio.create_task(self.recent_ac(username=username, sleep_sec=sleep_sec))
        stats_task = asyncio.create_task(self.submit_stats(username=username, sleep_sec=sleep_sec))

        recent_result, stats_result = await asyncio.gather(recent_task, stats_task, return_exceptions=True)

        recent_value = []
        if isinstance(recent_result, list):
            recent_value = recent_result

        stats_value: Optional[Dict[str, Any]] = None
        if isinstance(stats_result, dict):
            stats_value = stats_result

        return {"meta": meta, "recent_accepted": recent_value, "stats": stats_value}

    def _raise_if_item_error(self, items: List[Dict[str, Any]], context: str) -> None:
        """将 spider 产出的 `_error` 字段升级为业务异常。"""
        for row in items:
            error = row.get("_error")
            if error:
                raise UpstreamRequestError(f"{context}: {error}")


def format_local_time(ts: int) -> str:
    """将 Unix 秒级时间戳转换为本地时间字符串。"""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
