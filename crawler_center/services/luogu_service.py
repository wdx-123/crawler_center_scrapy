"""Luogu 业务服务实现。"""

from __future__ import annotations

from typing import Any, Dict

from crawler_center.core.config import AppSettings
from crawler_center.core.errors import UpstreamRequestError
from crawler_center.crawler.runner import ScrapyRunnerService
from crawler_center.crawler.spiders.luogu_practice import LuoguPracticeSpider

class LuoguService:
    # Luogu 抓取能力服务 

    def __init__(self, runner: ScrapyRunnerService, settings: AppSettings) -> None:
        self._runner = runner
        self._settings = settings

    async def practice(self, uid: int, sleep_sec: float) -> Dict[str, Any]:
        """抓取用户练题数据。"""
        items = await self._runner.run(
            LuoguPracticeSpider,
            base_url=self._settings.luogu_base_url,
            uid=uid,
            sleep_sec=sleep_sec,
        )

        for row in items:
            error = row.get("_error")
            if error:
                raise UpstreamRequestError(f"luogu practice: {error}")

        # 无结果时返回稳定空结构，减少上层判空分支。
        if not items:
            return {"user": None, "passed": [], "passed_count": 0}

        return dict(items[0])
s