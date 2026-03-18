"""Lanqiao 做题统计 spider。"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable

import scrapy

from crawler_center.services.proxy_service import TargetSite


class LanqiaoSolveStatsSpider(scrapy.Spider):
    """登录蓝桥并抓取提交列表。"""

    name = "lanqiao_solve_stats"
    target_site = TargetSite.LANQIAO.value
    auth_failed_error = "Lanqiao credentials invalid"
    auth_failed_error_code = "upstream_auth_failed"
    auth_failed_codes = {"20000", "30000"}
    auth_failed_message_hints = (
        "未注册",
        "密码错误",
        "登录失败",
        "账号或密码",
        "账户或密码",
        "用户不存在",
        "invalid credentials",
        "login failed",
        "unauthorized",
        "forbidden",
    )

    def __init__(
        self,
        base_url: str,
        login_url: str,
        user_url: str,
        phone: str,
        password: str,
        sync_num: int,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")
        self.login_url = login_url
        self.user_url = user_url
        self.phone = phone
        self.password = password
        self.sync_num = int(sync_num)
        self._fetched_count = 0

    async def start(self):
        """兼容 Scrapy 2.13+ 的异步入口，复用既有请求构造逻辑。"""
        for request in self.start_requests():
            yield request

    def start_requests(self):
        """先访问主站，获取会话与风控 cookie。"""
        yield scrapy.Request(
            url=f"{self.base_url}/",
            callback=self.parse_warmup,
            dont_filter=True,
            meta=self._request_meta(allow_http_errors=True),
        )

    def parse_warmup(self, response: scrapy.http.Response):
        """预热后发起登录请求。"""
        payload = {"login_str": self.phone, "password": self.password, "usertype": 0}
        yield scrapy.Request(
            url=self.login_url,
            method="POST",
            body=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "Origin": "https://passport.lanqiao.cn",
                "Referer": "https://passport.lanqiao.cn/login/",
                "Accept": "application/json, text/plain, */*",
            },
            callback=self.parse_login,
            dont_filter=True,
            meta=self._request_meta(allow_http_errors=True),
        )

    def parse_login(self, response: scrapy.http.Response):
        """校验登录接口返回并继续验证登录态。"""
        try:
            data = response.json()
        except Exception:
            if response.status >= 400:
                yield {"_error": f"Lanqiao login HTTP {response.status}", "_stage": "login", "_status": response.status}
                return
            yield {"_error": "Lanqiao login response is not valid JSON", "_stage": "login_json"}
            return

        if self._is_auth_failure_payload(data):
            yield self._auth_failure_item(stage="login")
            return

        if response.status >= 400:
            yield {"_error": f"Lanqiao login HTTP {response.status}", "_stage": "login", "_status": response.status}
            return

        yield scrapy.Request(
            url=self.user_url,
            headers={"Referer": "https://passport.lanqiao.cn/login/"},
            callback=self.parse_user,
            dont_filter=True,
            meta=self._request_meta(allow_http_errors=True),
        )

    def parse_user(self, response: scrapy.http.Response):
        """验证登录态有效后开始拉取提交分页。"""
        if response.status in {401, 403}:
            yield self._auth_failure_item(stage="user_check")
            return

        if response.status != 200:
            yield {"_error": f"Lanqiao user check HTTP {response.status}", "_stage": "user_check", "_status": response.status}
            return

        try:
            data = response.json()
        except Exception:
            yield {"_error": "Lanqiao user check response is not valid JSON", "_stage": "user_check_json"}
            return

        if not isinstance(data, dict):
            yield {"_error": "Lanqiao user check payload is not object", "_stage": "user_check_payload"}
            return

        if not data.get("id"):
            yield self._auth_failure_item(stage="user_check_login")
            return

        yield scrapy.Request(
            url=f"{self.base_url}/api/v2/problems/submissions/?page_size=100",
            headers={"Referer": f"{self.base_url}/"},
            callback=self.parse_submissions,
            dont_filter=True,
            meta=self._request_meta(allow_http_errors=True),
        )

    def parse_submissions(self, response: scrapy.http.Response):
        """按分页抓取提交记录，并按 sync_num 控制抓取条数。"""
        if response.status >= 400:
            yield {
                "_error": f"Lanqiao submissions HTTP {response.status}",
                "_stage": "submissions",
                "_status": response.status,
            }
            return

        try:
            payload = response.json()
        except Exception:
            yield {"_error": "Lanqiao submissions response is not valid JSON", "_stage": "submissions_json"}
            return

        if not isinstance(payload, dict):
            yield {"_error": "Lanqiao submissions payload is not object", "_stage": "submissions_payload"}
            return

        rows = payload.get("results")
        if not isinstance(rows, list):
            yield {"_error": "Lanqiao submissions results is not list", "_stage": "submissions_results"}
            return

        emitted_rows = self._trim_rows(rows)
        for row in emitted_rows:
            if isinstance(row, dict):
                yield row

        if self.sync_num > 0 and self._fetched_count >= self.sync_num:
            return

        next_url = payload.get("next")
        if isinstance(next_url, str) and next_url:
            yield scrapy.Request(
                url=next_url,
                headers={"Referer": f"{self.base_url}/"},
                callback=self.parse_submissions,
                dont_filter=True,
                meta=self._request_meta(allow_http_errors=True),
            )

    def _request_meta(self, *, allow_http_errors: bool = False) -> Dict[str, Any]:
        meta: Dict[str, Any] = {"target_site": self.target_site}
        if allow_http_errors:
            meta["handle_httpstatus_all"] = True
        return meta

    def _auth_failure_item(self, stage: str) -> Dict[str, Any]:
        return {
            "_error": self.auth_failed_error,
            "_stage": stage,
            "_error_code": self.auth_failed_error_code,
        }

    def _is_auth_failure_payload(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        code = payload.get("code")
        if code is not None and str(code) in self.auth_failed_codes:
            return True
        for field in ("message", "msg", "detail", "error"):
            value = payload.get(field)
            if isinstance(value, str) and self._contains_auth_failure_message(value):
                return True
        return False

    def _contains_auth_failure_message(self, message: str) -> bool:
        normalized = message.strip().lower()
        return any(hint in normalized for hint in self.auth_failed_message_hints)

    def _trim_rows(self, rows: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:
        if self.sync_num <= 0:
            return list(rows)
        left = self.sync_num - self._fetched_count
        if left <= 0:
            return []
        selected = list(rows)[:left]
        self._fetched_count += len(selected)
        return selected
