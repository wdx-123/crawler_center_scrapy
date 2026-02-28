from __future__ import annotations

from crawler_center.services.proxy_service import ProxyService


def _build_service() -> ProxyService:
    return ProxyService(
        probe_urls={
            "leetcode": "https://leetcode.cn/",
            "luogu": "https://www.luogu.com.cn/",
            "lanqiao": "https://www.lanqiao.cn/",
        },
        user_agent="pytest-agent",
        request_timeout_sec=2,
    )


def test_sync_replace_and_remove() -> None:
    service = _build_service()

    first = service.sync_replace(["http://p1", "http://p2", "http://p2"])
    assert first == {"total": 2, "added": 2, "updated": 0, "removed": 0}

    second = service.sync_replace(["http://p2", "http://p3"])
    assert second == {"total": 2, "added": 1, "updated": 1, "removed": 1}

    removed = service.remove(["http://p2", "http://missing"])
    assert removed == {"total": 1, "removed": 1}


def test_target_health_isolated() -> None:
    service = _build_service()
    service.sync_replace(["http://p1"])

    selected = service.acquire_proxy("leetcode")
    assert selected == "http://p1"

    service.report_failure("http://p1", "leetcode")
    service.report_failure("http://p1", "leetcode")

    snapshot = service.get_snapshot()
    assert snapshot[0]["health_by_target"]["leetcode"]["status"] == "SUSPECT"
    assert snapshot[0]["health_by_target"]["luogu"]["status"] == "OK"

    service.report_failure("http://p1", "leetcode")
    snapshot = service.get_snapshot()
    assert snapshot[0]["health_by_target"]["leetcode"]["status"] == "DEAD"

    service.report_success("http://p1", "luogu", latency_ms=20)
    snapshot = service.get_snapshot()
    assert snapshot[0]["health_by_target"]["luogu"]["status"] == "OK"
    assert snapshot[0]["health_by_target"]["leetcode"]["status"] == "DEAD"


def test_list_proxies_default_sort_and_summary() -> None:
    service = _build_service()
    service.sync_replace(["http://p1", "http://p2", "http://p3"])

    service.report_failure("http://p2", "leetcode")
    service.report_failure("http://p2", "leetcode")

    service.report_failure("http://p3", "leetcode")
    service.report_failure("http://p3", "leetcode")
    service.report_failure("http://p3", "leetcode")

    result = service.list_proxies()
    assert [item["proxy_url"] for item in result["items"]] == ["http://p1", "http://p2", "http://p3"]
    assert [item["status"] for item in result["items"]] == ["OK", "SUSPECT", "DEAD"]
    assert [item["status_label"] for item in result["items"]] == ["好", "中", "坏"]
    assert result["summary"]["total"] == 3
    assert result["summary"]["by_global_status"] == {"OK": 1, "SUSPECT": 1, "DEAD": 1}
    assert result["summary"]["applied_filters"] == {
        "global_status": None,
        "target_site": None,
        "target_status": None,
    }


def test_list_proxies_target_filters_and_sorting() -> None:
    service = _build_service()
    service.sync_replace(["http://p1", "http://p2", "http://p3"])

    # p1: global SUSPECT, leetcode OK
    service.report_failure("http://p1", "luogu")
    service.report_failure("http://p1", "luogu")

    # p2: global SUSPECT, leetcode SUSPECT
    service.report_failure("http://p2", "leetcode")
    service.report_failure("http://p2", "leetcode")

    # p3: global DEAD, leetcode DEAD
    service.report_failure("http://p3", "leetcode")
    service.report_failure("http://p3", "leetcode")
    service.report_failure("http://p3", "leetcode")

    by_target = service.list_proxies(target_site="leetcode")
    assert [item["proxy_url"] for item in by_target["items"]] == ["http://p1", "http://p2", "http://p3"]
    assert [item["health_by_target"]["leetcode"]["status"] for item in by_target["items"]] == [
        "OK",
        "SUSPECT",
        "DEAD",
    ]

    target_filtered = service.list_proxies(target_site="leetcode", target_status="SUSPECT")
    assert [item["proxy_url"] for item in target_filtered["items"]] == ["http://p2"]
    assert target_filtered["summary"]["by_global_status"] == {"OK": 0, "SUSPECT": 1, "DEAD": 0}

    combined = service.list_proxies(global_status="SUSPECT", target_site="leetcode", target_status="OK")
    assert [item["proxy_url"] for item in combined["items"]] == ["http://p1"]
    assert combined["summary"]["applied_filters"] == {
        "global_status": "SUSPECT",
        "target_site": "leetcode",
        "target_status": "OK",
    }
