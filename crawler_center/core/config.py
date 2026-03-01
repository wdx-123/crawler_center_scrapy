"""应用配置加载与归一化。

生产环境中配置优先级采用：
1) 环境变量（最高优先级）
2) config.yaml
3) 代码内默认值（兜底）

该模块确保即使配置缺失或类型异常，系统也能回退到安全默认值并继续启动。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


def _as_int(value: Any, default: int) -> int:
    """将输入安全转换为 int，失败时返回默认值。"""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    """将输入安全转换为 float，失败时返回默认值。"""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class AppSettings:
    """应用运行时配置快照。

    该对象在应用启动时一次性构建，并通过 `app.state.settings` 在全局共享。
    """

    leetcode_base_url: str
    luogu_base_url: str
    lanqiao_base_url: str
    lanqiao_login_url: str
    lanqiao_user_url: str
    default_timeout_sec: int
    default_sleep_sec: float
    default_user_agent: str
    api_title: str
    api_version: str
    crawler_run_timeout_sec: int
    crawler_concurrent_requests: int
    crawler_retry_times: int
    proxy_active_probe_interval_sec: int
    internal_token: Optional[str]
    log_level: str
    config_path: Path

    @property
    def probe_urls(self) -> Dict[str, str]:
        """返回代理主动探测使用的目标站点 URL。"""
        return {
            "leetcode": f"{self.leetcode_base_url.rstrip('/')}/",
            "luogu": f"{self.luogu_base_url.rstrip('/')}/",
            "lanqiao": f"{self.lanqiao_base_url.rstrip('/')}/",
        }


def _resolve_config_path(path: str) -> Path:
    """解析配置路径。

    先按调用方传入路径查找；若不存在，再尝试仓库根目录下的同名路径。
    """
    candidate = Path(path)
    if candidate.exists():
        return candidate

    project_candidate = Path(__file__).resolve().parents[2] / path
    if project_candidate.exists():
        return project_candidate

    return candidate


def load_settings(path: str = "config.yaml") -> AppSettings:
    """加载并标准化应用配置。

    参数:
    - path: 配置文件路径，默认 `config.yaml`。

    返回:
    - `AppSettings` 不可变配置对象，可安全在多协程中共享读取。
    """
    yaml_path = _resolve_config_path(path)
    data: Dict[str, Any] = {}
    if yaml_path.exists():
        with yaml_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}

    leetcode_conf = data.get("leetcode", {})
    luogu_conf = data.get("luogu", {})
    lanqiao_conf = data.get("lanqiao", {})
    crawler_conf = data.get("crawler", {})
    api_conf = data.get("api", {})
    internal_conf = data.get("internal", {})

    leetcode_base_url = os.getenv("LEETCODE_BASE_URL", leetcode_conf.get("base_url", "https://leetcode.cn"))
    luogu_base_url = os.getenv("LUOGU_BASE_URL", luogu_conf.get("base_url", "https://www.luogu.com.cn"))
    lanqiao_base_url = os.getenv("LANQIAO_BASE_URL", lanqiao_conf.get("base_url", "https://www.lanqiao.cn"))
    lanqiao_login_url = os.getenv(
        "LANQIAO_LOGIN_URL",
        lanqiao_conf.get("login_url", "https://passport.lanqiao.cn/api/v1/login/?auth_type=login"),
    )
    lanqiao_user_url = os.getenv(
        "LANQIAO_USER_URL", lanqiao_conf.get("user_url", "https://passport.lanqiao.cn/api/v1/user/")
    )

    default_timeout_sec = _as_int(os.getenv("DEFAULT_TIMEOUT_SEC", crawler_conf.get("default_timeout", 15)), 15)
    default_sleep_sec = _as_float(os.getenv("DEFAULT_SLEEP_SEC", crawler_conf.get("default_sleep_sec", 0.8)), 0.8)
    default_user_agent = os.getenv(
        "DEFAULT_USER_AGENT",
        crawler_conf.get(
            "default_user_agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36",
        ),
    )

    api_title = os.getenv("API_TITLE", api_conf.get("title", "crawler_center"))
    api_version = os.getenv("API_VERSION", api_conf.get("version", "2.0.0"))

    crawler_run_timeout_sec = _as_int(
        os.getenv("CRAWLER_RUN_TIMEOUT_SEC", crawler_conf.get("run_timeout_sec", 30)),
        30,
    )
    crawler_concurrent_requests = _as_int(
        os.getenv("CRAWLER_CONCURRENT_REQUESTS", crawler_conf.get("concurrent_requests", 16)),
        16,
    )
    crawler_retry_times = _as_int(os.getenv("CRAWLER_RETRY_TIMES", crawler_conf.get("retry_times", 2)), 2)

    proxy_active_probe_interval_sec = _as_int(
        os.getenv(
            "PROXY_ACTIVE_PROBE_INTERVAL_SEC",
            crawler_conf.get("proxy_active_probe_interval_sec", 300),
        ),
        300,
    )

    token_from_env = os.getenv("INTERNAL_TOKEN")
    # Treat empty string as not set to avoid overriding config with empty value
    if token_from_env == "":
        token_from_env = None

    token_from_yaml = internal_conf.get("token")
    internal_token = token_from_env if token_from_env is not None else token_from_yaml

    log_level = os.getenv("LOG_LEVEL", data.get("logging", {}).get("level", "INFO"))

    return AppSettings(
        leetcode_base_url=str(leetcode_base_url),
        luogu_base_url=str(luogu_base_url),
        lanqiao_base_url=str(lanqiao_base_url),
        lanqiao_login_url=str(lanqiao_login_url),
        lanqiao_user_url=str(lanqiao_user_url),
        default_timeout_sec=default_timeout_sec,
        default_sleep_sec=default_sleep_sec,
        default_user_agent=str(default_user_agent),
        api_title=str(api_title),
        api_version=str(api_version),
        crawler_run_timeout_sec=crawler_run_timeout_sec,
        crawler_concurrent_requests=crawler_concurrent_requests,
        crawler_retry_times=crawler_retry_times,
        proxy_active_probe_interval_sec=proxy_active_probe_interval_sec,
        internal_token=internal_token,
        log_level=str(log_level).upper(),
        config_path=yaml_path,
    )
