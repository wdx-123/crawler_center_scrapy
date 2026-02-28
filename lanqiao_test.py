"""Lanqiao 本地调试 demo（复用项目 Scrapy 架构）。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any, Dict

from crawler_center.core.config import load_settings
from crawler_center.crawler.runner import ScrapyRunnerService
from crawler_center.services.lanqiao_service import LanqiaoService
from crawler_center.services.proxy_service import ProxyService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lanqiao solve_stats demo")
    parser.add_argument("--phone", type=str, default=os.getenv("LQ_PHONE", ""), help="蓝桥手机号")
    parser.add_argument("--password", type=str, default=os.getenv("LQ_PASS", ""), help="蓝桥密码")
    parser.add_argument("--sync_num", type=int, default=0, help="-1: stats only; 0: full; >0: incremental")
    return parser.parse_args()


async def run_demo(phone: str, password: str, sync_num: int) -> Dict[str, Any]:
    settings = load_settings()
    proxy_service = ProxyService(
        probe_urls=settings.probe_urls,
        user_agent=settings.default_user_agent,
        request_timeout_sec=settings.default_timeout_sec,
    )
    runner = ScrapyRunnerService.get_instance(app_settings=settings, proxy_service=proxy_service)
    service = LanqiaoService(runner=runner, settings=settings)
    return await service.solve_stats(phone=phone, password=password, sync_num=sync_num)


def main() -> None:
    args = parse_args()
    if not args.phone or not args.password:
        raise SystemExit("missing credentials: provide --phone/--password or env LQ_PHONE/LQ_PASS")

    data = asyncio.run(run_demo(phone=args.phone, password=args.password, sync_num=args.sync_num))
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
