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
