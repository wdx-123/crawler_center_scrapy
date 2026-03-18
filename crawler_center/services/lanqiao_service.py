"""Lanqiao 业务服务实现。"""

from __future__ import annotations

from typing import Any, Dict, List

from crawler_center.core.config import AppSettings
from crawler_center.core.errors import UpstreamAuthenticationError, UpstreamRequestError
from crawler_center.crawler.parsers.lanqiao_parser import build_solve_stats_payload
from crawler_center.crawler.runner import ScrapyRunnerService
from crawler_center.crawler.spiders.lanqiao_solve_stats import LanqiaoSolveStatsSpider


class LanqiaoService:
    """Lanqiao 抓取能力聚合服务。"""

    def __init__(self, runner: ScrapyRunnerService, settings: AppSettings) -> None:
        self._runner = runner
        self._settings = settings

    async def solve_stats(self, phone: str, password: str, sync_num: int) -> Dict[str, Any]:
        """抓取用户做题统计信息。"""
        items = await self._runner.run(
            LanqiaoSolveStatsSpider,
            base_url=self._settings.lanqiao_base_url,
            login_url=self._settings.lanqiao_login_url,
            user_url=self._settings.lanqiao_user_url,
            phone=phone,
            password=password,
            sync_num=sync_num,
        )
        self._raise_if_item_error(items, "lanqiao solve_stats")
        return build_solve_stats_payload(submissions=items, sync_num=sync_num)

    def _raise_if_item_error(self, items: List[Dict[str, Any]], context: str) -> None:
        for row in items:
            error = row.get("_error")
            if error:
                if row.get("_error_code") == "upstream_auth_failed":
                    raise UpstreamAuthenticationError(str(error))
                stage = row.get("_stage")
                if stage:
                    raise UpstreamRequestError(f"{context}: [{stage}] {error}")
                raise UpstreamRequestError(f"{context}: {error}")
