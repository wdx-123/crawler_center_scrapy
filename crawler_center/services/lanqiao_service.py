"""Lanqiao 业务服务骨架。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from crawler_center.core.config import AppSettings
from crawler_center.crawler.runner import ScrapyRunnerService


@dataclass
class LanqiaoCookie:
    """登录结果中的 cookie 信息载体。"""

    cookie_header: str
    cookies: Optional[Dict[str, str]] = None


class LanqiaoService:
    """Lanqiao 业务服务。

    当前方法尚未实现，用于保留协议与后续扩展点。
    """

    def __init__(self, runner: ScrapyRunnerService, settings: AppSettings) -> None:
        self._runner = runner
        self._settings = settings

    async def login(self, username: str, password: str) -> LanqiaoCookie:
        """执行登录流程并返回 cookie 信息。"""
        raise NotImplementedError("Lanqiao login not implemented yet")

    async def solve_stats(self, cookie_header: Optional[str], user_id: Optional[str]) -> Dict[str, Any]:
        """抓取用户做题统计信息。"""
        raise NotImplementedError("Lanqiao solve_stats not implemented yet")
