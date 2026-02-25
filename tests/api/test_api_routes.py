from __future__ import annotations

from fastapi.testclient import TestClient

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


def test_lanqiao_stub_returns_501() -> None:
    app = create_test_app()
    with TestClient(app) as client:
        response = client.post("/v2/lanqiao/login", json={"username": "u", "password": "p"})

    assert response.status_code == 501


def test_internal_token_missing_returns_503() -> None:
    app = create_test_app(internal_token=None)
    with TestClient(app) as client:
        response = client.post("/internal/proxies/sync", json={"proxies": ["http://127.0.0.1:9000"]})

    assert response.status_code == 503


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
