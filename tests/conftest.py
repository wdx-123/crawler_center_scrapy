from __future__ import annotations

from pathlib import Path
from typing import Optional

from crawler_center.api.main import create_app
from crawler_center.core.config import AppSettings
from crawler_center.crawler.runner import ScrapyRunnerService


def build_test_settings(internal_token: Optional[str] = None) -> AppSettings:
    return AppSettings(
        leetcode_base_url="https://leetcode.cn",
        luogu_base_url="https://www.luogu.com.cn",
        lanqiao_base_url="https://www.lanqiao.cn",
        lanqiao_login_url="https://passport.lanqiao.cn/api/v1/login/?auth_type=login",
        lanqiao_user_url="https://passport.lanqiao.cn/api/v1/user/",
        default_timeout_sec=10,
        default_sleep_sec=0.0,
        default_user_agent="pytest-agent",
        api_title="crawler_center_test",
        api_version="2.0.0-test",
        crawler_run_timeout_sec=3,
        crawler_concurrent_requests=8,
        crawler_retry_times=1,
        proxy_active_probe_interval_sec=300,
        internal_token=internal_token,
        log_level="INFO",
        config_path=Path("config.yaml"),
    )


def create_test_app(internal_token: Optional[str] = None):
    ScrapyRunnerService.reset_instance_for_tests()
    return create_app(app_settings=build_test_settings(internal_token=internal_token))
