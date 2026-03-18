from __future__ import annotations

import json

import scrapy
from scrapy.http import HtmlResponse, Request, TextResponse

from crawler_center.crawler.spiders.lanqiao_solve_stats import LanqiaoSolveStatsSpider
from crawler_center.crawler.spiders.leetcode_recent_ac import LeetCodeRecentAcSpider


def test_leetcode_graphql_request_builder_exists_and_works() -> None:
    spider = LeetCodeRecentAcSpider(base_url="https://leetcode.cn", username="demo")

    request = spider.build_graphql_request(
        url=spider.graphql_noj_url(),
        operation_name="recentACSubmissions",
        query="query recentACSubmissions($userSlug: String!) { recentACSubmissions(userSlug: $userSlug) { submitTime } }",
        variables={"userSlug": "demo"},
        referer=spider.profile_url(),
        csrf_token="",
        callback=spider.parse_graphql,
    )

    assert request.method == "POST"
    assert request.meta.get("target_site") == spider.target_site
    assert request.url == spider.graphql_noj_url()


def test_lanqiao_requests_carry_target_site_meta() -> None:
    spider = LanqiaoSolveStatsSpider(
        base_url="https://www.lanqiao.cn",
        login_url="https://passport.lanqiao.cn/api/v1/login/?auth_type=login",
        user_url="https://passport.lanqiao.cn/api/v1/user/",
        phone="13800000000",
        password="pwd",
        sync_num=0,
    )

    warmup_request = next(spider.start_requests())
    assert warmup_request.meta.get("target_site") == spider.target_site
    assert warmup_request.meta.get("handle_httpstatus_all") is True

    warmup_response = HtmlResponse(
        url="https://www.lanqiao.cn/",
        body=b"<html></html>",
        encoding="utf-8",
        request=Request(url="https://www.lanqiao.cn/"),
    )
    login_request = next(spider.parse_warmup(warmup_response))
    assert login_request.meta.get("target_site") == spider.target_site
    assert login_request.meta.get("handle_httpstatus_all") is True
    assert login_request.method == "POST"

    login_ok_response = TextResponse(
        url=spider.login_url,
        body=b"{}",
        status=200,
        encoding="utf-8",
        request=Request(url=spider.login_url),
    )
    user_request = next(spider.parse_login(login_ok_response))
    assert user_request.meta.get("target_site") == spider.target_site
    assert user_request.meta.get("handle_httpstatus_all") is True

    user_ok_response = TextResponse(
        url=spider.user_url,
        body=b'{"id": 1}',
        status=200,
        encoding="utf-8",
        request=Request(url=spider.user_url),
    )
    submissions_request = next(spider.parse_user(user_ok_response))
    assert submissions_request.meta.get("target_site") == spider.target_site
    assert submissions_request.meta.get("handle_httpstatus_all") is True


def test_lanqiao_login_json_error_reports_item_error() -> None:
    spider = LanqiaoSolveStatsSpider(
        base_url="https://www.lanqiao.cn",
        login_url="https://passport.lanqiao.cn/api/v1/login/?auth_type=login",
        user_url="https://passport.lanqiao.cn/api/v1/user/",
        phone="13800000000",
        password="pwd",
        sync_num=0,
    )

    bad_login_response = TextResponse(
        url=spider.login_url,
        body=b"<html>bad</html>",
        status=200,
        encoding="utf-8",
        request=Request(url=spider.login_url),
    )
    rows = list(spider.parse_login(bad_login_response))

    assert rows == [{"_error": "Lanqiao login response is not valid JSON", "_stage": "login_json"}]


def test_lanqiao_login_business_error_reports_auth_failure() -> None:
    spider = LanqiaoSolveStatsSpider(
        base_url="https://www.lanqiao.cn",
        login_url="https://passport.lanqiao.cn/api/v1/login/?auth_type=login",
        user_url="https://passport.lanqiao.cn/api/v1/user/",
        phone="13800000000",
        password="pwd",
        sync_num=0,
    )

    bad_login_response = TextResponse(
        url=spider.login_url,
        body=b'{"code":20000,"message":"\xe6\x9c\xaa\xe6\xb3\xa8\xe5\x86\x8c\xe7\x94\xa8\xe6\x88\xb7"}',
        status=404,
        encoding="utf-8",
        request=Request(url=spider.login_url),
    )
    rows = list(spider.parse_login(bad_login_response))

    assert rows == [
        {"_error": "Lanqiao credentials invalid", "_stage": "login", "_error_code": "upstream_auth_failed"}
    ]


def test_lanqiao_user_check_403_reports_auth_failure() -> None:
    spider = LanqiaoSolveStatsSpider(
        base_url="https://www.lanqiao.cn",
        login_url="https://passport.lanqiao.cn/api/v1/login/?auth_type=login",
        user_url="https://passport.lanqiao.cn/api/v1/user/",
        phone="13800000000",
        password="pwd",
        sync_num=0,
    )

    user_response = TextResponse(
        url=spider.user_url,
        body=b'{"code":30000}',
        status=403,
        encoding="utf-8",
        request=Request(url=spider.user_url),
    )
    rows = list(spider.parse_user(user_response))

    assert rows == [
        {"_error": "Lanqiao credentials invalid", "_stage": "user_check", "_error_code": "upstream_auth_failed"}
    ]


def test_lanqiao_user_check_without_id_reports_auth_failure() -> None:
    spider = LanqiaoSolveStatsSpider(
        base_url="https://www.lanqiao.cn",
        login_url="https://passport.lanqiao.cn/api/v1/login/?auth_type=login",
        user_url="https://passport.lanqiao.cn/api/v1/user/",
        phone="13800000000",
        password="pwd",
        sync_num=0,
    )

    user_response = TextResponse(
        url=spider.user_url,
        body=b'{"phone":"13800000000"}',
        status=200,
        encoding="utf-8",
        request=Request(url=spider.user_url),
    )
    rows = list(spider.parse_user(user_response))

    assert rows == [
        {
            "_error": "Lanqiao credentials invalid",
            "_stage": "user_check_login",
            "_error_code": "upstream_auth_failed",
        }
    ]


def test_lanqiao_sync_num_limit_stops_pagination() -> None:
    spider = LanqiaoSolveStatsSpider(
        base_url="https://www.lanqiao.cn",
        login_url="https://passport.lanqiao.cn/api/v1/login/?auth_type=login",
        user_url="https://passport.lanqiao.cn/api/v1/user/",
        phone="13800000000",
        password="pwd",
        sync_num=2,
    )

    payload = {
        "results": [
            {"problem_id": 1, "problem_name": "A", "is_passed": True, "created_at": "2025-01-01T00:00:00+08:00"},
            {"problem_id": 2, "problem_name": "B", "is_passed": False, "created_at": "2025-01-02T00:00:00+08:00"},
            {"problem_id": 3, "problem_name": "C", "is_passed": True, "created_at": "2025-01-03T00:00:00+08:00"},
        ],
        "next": "https://www.lanqiao.cn/api/v2/problems/submissions/?page=2&page_size=100",
    }
    response = TextResponse(
        url="https://www.lanqiao.cn/api/v2/problems/submissions/?page_size=100",
        body=json.dumps(payload).encode("utf-8"),
        status=200,
        encoding="utf-8",
        request=Request(url="https://www.lanqiao.cn/api/v2/problems/submissions/?page_size=100"),
    )

    out = list(spider.parse_submissions(response))
    rows = [item for item in out if isinstance(item, dict)]
    next_requests = [item for item in out if isinstance(item, scrapy.Request)]

    assert len(rows) == 2
    assert next_requests == []


def test_lanqiao_empty_submissions_are_stable() -> None:
    spider = LanqiaoSolveStatsSpider(
        base_url="https://www.lanqiao.cn",
        login_url="https://passport.lanqiao.cn/api/v1/login/?auth_type=login",
        user_url="https://passport.lanqiao.cn/api/v1/user/",
        phone="13800000000",
        password="pwd",
        sync_num=0,
    )

    response = TextResponse(
        url="https://www.lanqiao.cn/api/v2/problems/submissions/?page_size=100",
        body=b'{"results":[],"next":null}',
        status=200,
        encoding="utf-8",
        request=Request(url="https://www.lanqiao.cn/api/v2/problems/submissions/?page_size=100"),
    )

    assert list(spider.parse_submissions(response)) == []
