from __future__ import annotations

from fastapi.testclient import TestClient

from crawler_center.core.errors import UpstreamAuthenticationError
from tests.conftest import create_test_app


def test_healthz_route() -> None:
    app = create_test_app()
    with TestClient(app) as client:
        response = client.get("/v2/healthz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["status"] == "ok"


def test_leetcode_profile_meta_contract() -> None:
    app = create_test_app()
    with TestClient(app) as client:
        async def fake_profile_meta(username: str, sleep_sec: float):
            return {
                "exists": True,
                "url_final": f"https://leetcode.cn/u/{username}/",
                "og_title": "t",
                "og_description": "d",
            }

        client.app.state.leetcode_service.profile_meta = fake_profile_meta
        response = client.post("/v2/leetcode/profile_meta", json={"username": "demo", "sleep_sec": 0})

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "ok": True,
        "data": {
            "meta": {
                "exists": True,
                "url_final": "https://leetcode.cn/u/demo/",
                "og_title": "t",
                "og_description": "d",
            }
        },
    }


def test_leetcode_profile_meta_validation() -> None:
    app = create_test_app()
    with TestClient(app) as client:
        response = client.post("/v2/leetcode/profile_meta", json={"username": "", "sleep_sec": 0})

    assert response.status_code == 422
    payload = response.json()
    assert payload["ok"] is False
    assert payload["code"] == "validation_error"


def test_lanqiao_solve_stats_contract_modes() -> None:
    app = create_test_app()
    with TestClient(app) as client:
        async def fake_solve_stats(phone: str, password: str, sync_num: int):
            assert phone == "13800000000"
            assert password == "pwd"
            if sync_num == -1:
                return {"stats": {"total_passed": 5, "total_failed": 2}}
            if sync_num == 0:
                return {
                    "stats": {"total_passed": 5, "total_failed": 2},
                    "problems": [
                        {
                            "problem_name": "带分数",
                            "problem_id": 208,
                            "created_at": "2025-02-09T10:24:00.517000+08:00",
                            "is_passed": True,
                        }
                    ],
                }
            return {
                "problems": [
                    {
                        "problem_name": "带分数",
                        "problem_id": 208,
                        "created_at": "2025-02-09T10:24:00.517000+08:00",
                        "is_passed": True,
                    }
                ]
            }

        client.app.state.lanqiao_service.solve_stats = fake_solve_stats

        stats_only = client.post(
            "/v2/lanqiao/solve_stats",
            json={"phone": "13800000000", "password": "pwd", "sync_num": -1},
        )
        full_sync = client.post(
            "/v2/lanqiao/solve_stats",
            json={"phone": "13800000000", "password": "pwd", "sync_num": 0},
        )
        incremental = client.post(
            "/v2/lanqiao/solve_stats",
            json={"phone": "13800000000", "password": "pwd", "sync_num": 3},
        )

    assert stats_only.status_code == 200
    assert stats_only.json() == {
        "ok": True,
        "data": {"stats": {"total_passed": 5, "total_failed": 2}},
    }

    assert full_sync.status_code == 200
    assert "stats" in full_sync.json()["data"]
    assert "problems" in full_sync.json()["data"]

    assert incremental.status_code == 200
    assert "stats" not in incremental.json()["data"]
    assert len(incremental.json()["data"]["problems"]) == 1


def test_lanqiao_solve_stats_validation() -> None:
    app = create_test_app()
    with TestClient(app) as client:
        response = client.post(
            "/v2/lanqiao/solve_stats",
            json={"phone": "13800000000", "password": "pwd", "sync_num": -2},
        )

    assert response.status_code == 422
    payload = response.json()
    assert payload["ok"] is False
    assert payload["code"] == "validation_error"


def test_lanqiao_solve_stats_auth_failure_returns_401() -> None:
    app = create_test_app()
    with TestClient(app) as client:
        async def fake_solve_stats(phone: str, password: str, sync_num: int):
            assert phone == "13800000000"
            assert password == "pwd"
            assert sync_num == 0
            raise UpstreamAuthenticationError("Lanqiao credentials invalid")

        client.app.state.lanqiao_service.solve_stats = fake_solve_stats
        response = client.post(
            "/v2/lanqiao/solve_stats",
            json={"phone": "13800000000", "password": "pwd", "sync_num": 0},
        )

    assert response.status_code == 401
    assert response.json() == {
        "ok": False,
        "error": "Lanqiao credentials invalid",
        "code": "upstream_auth_failed",
    }


def test_lanqiao_login_route_removed_returns_404_with_unified_error() -> None:
    app = create_test_app()
    with TestClient(app) as client:
        response = client.post("/v2/lanqiao/login", json={"username": "u", "password": "p"})

    assert response.status_code == 404
    payload = response.json()
    assert payload["ok"] is False
    assert payload["code"] == "http_error"


def test_internal_token_missing_returns_503() -> None:
    app = create_test_app(internal_token=None)
    with TestClient(app) as client:
        response = client.post("/internal/proxies/sync", json={"proxies": ["http://127.0.0.1:9000"]})
        list_response = client.get("/internal/proxies")

    assert response.status_code == 503
    assert list_response.status_code == 503


def test_internal_token_auth_and_sync_success() -> None:
    app = create_test_app(internal_token="secret-token")
    with TestClient(app) as client:
        unauthorized = client.post("/internal/proxies/sync", json={"proxies": ["http://127.0.0.1:9000"]})
        assert unauthorized.status_code == 401

        bad_token = client.post(
            "/internal/proxies/sync",
            json={"proxies": ["http://127.0.0.1:9000"]},
            headers={"X-Internal-Token": "wrong"},
        )
        assert bad_token.status_code == 401

        ok_response = client.post(
            "/internal/proxies/sync",
            json={"proxies": ["http://127.0.0.1:9000", "http://127.0.0.1:9001"]},
            headers={"X-Internal-Token": "secret-token", "X-Request-ID": "req-1"},
        )

    assert ok_response.status_code == 200
    payload = ok_response.json()
    assert payload["ok"] is True
    assert payload["data"]["total"] == 2
    assert payload["data"]["added"] == 2


def test_internal_proxy_list_auth_filter_and_validation() -> None:
    app = create_test_app(internal_token="secret-token")
    with TestClient(app) as client:
        unauthorized = client.get("/internal/proxies")
        assert unauthorized.status_code == 401

        bad_token = client.get("/internal/proxies", headers={"X-Internal-Token": "wrong"})
        assert bad_token.status_code == 401

        sync_response = client.post(
            "/internal/proxies/sync",
            json={
                "proxies": [
                    "http://127.0.0.1:9001",
                    "http://127.0.0.1:9002",
                    "http://127.0.0.1:9003",
                    "http://127.0.0.1:9004",
                ]
            },
            headers={"X-Internal-Token": "secret-token"},
        )
        assert sync_response.status_code == 200

        service = client.app.state.proxy_service

        # p1: global SUSPECT, leetcode OK
        service.report_failure("http://127.0.0.1:9001", "luogu")
        service.report_failure("http://127.0.0.1:9001", "luogu")

        # p2: global SUSPECT, leetcode SUSPECT
        service.report_failure("http://127.0.0.1:9002", "leetcode")
        service.report_failure("http://127.0.0.1:9002", "leetcode")

        # p3: global DEAD, leetcode DEAD
        service.report_failure("http://127.0.0.1:9003", "leetcode")
        service.report_failure("http://127.0.0.1:9003", "leetcode")
        service.report_failure("http://127.0.0.1:9003", "leetcode")

        all_list = client.get("/internal/proxies", headers={"X-Internal-Token": "secret-token"})
        assert all_list.status_code == 200
        payload = all_list.json()
        assert [item["proxy_url"] for item in payload["data"]["items"]] == [
            "http://127.0.0.1:9004",
            "http://127.0.0.1:9001",
            "http://127.0.0.1:9002",
            "http://127.0.0.1:9003",
        ]
        assert payload["data"]["items"][0]["status_label"] == "好"
        assert payload["data"]["summary"]["by_global_status"] == {"OK": 1, "SUSPECT": 2, "DEAD": 1}

        global_filtered = client.get(
            "/internal/proxies",
            params={"global_status": "DEAD"},
            headers={"X-Internal-Token": "secret-token"},
        )
        assert global_filtered.status_code == 200
        assert [item["proxy_url"] for item in global_filtered.json()["data"]["items"]] == [
            "http://127.0.0.1:9003"
        ]

        target_filtered = client.get(
            "/internal/proxies",
            params={"target_site": "leetcode", "target_status": "SUSPECT"},
            headers={"X-Internal-Token": "secret-token"},
        )
        assert target_filtered.status_code == 200
        assert [item["proxy_url"] for item in target_filtered.json()["data"]["items"]] == [
            "http://127.0.0.1:9002"
        ]

        combined_filtered = client.get(
            "/internal/proxies",
            params={"global_status": "SUSPECT", "target_site": "leetcode", "target_status": "OK"},
            headers={"X-Internal-Token": "secret-token"},
        )
        assert combined_filtered.status_code == 200
        assert [item["proxy_url"] for item in combined_filtered.json()["data"]["items"]] == [
            "http://127.0.0.1:9001"
        ]

        target_only_sort = client.get(
            "/internal/proxies",
            params={"target_site": "leetcode"},
            headers={"X-Internal-Token": "secret-token"},
        )
        assert target_only_sort.status_code == 200
        assert [item["proxy_url"] for item in target_only_sort.json()["data"]["items"]] == [
            "http://127.0.0.1:9001",
            "http://127.0.0.1:9004",
            "http://127.0.0.1:9002",
            "http://127.0.0.1:9003",
        ]

        invalid_query = client.get(
            "/internal/proxies",
            params={"target_status": "SUSPECT"},
            headers={"X-Internal-Token": "secret-token"},
        )
        assert invalid_query.status_code == 422
        invalid_payload = invalid_query.json()
        assert invalid_payload["ok"] is False
        assert invalid_payload["code"] == "validation_error"
