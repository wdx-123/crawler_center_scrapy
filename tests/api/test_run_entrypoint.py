from __future__ import annotations

import sys
import types

from crawler_center.api import run as run_entry


def _patch_dummy_app_module(monkeypatch):
    dummy_module = types.ModuleType("crawler_center.api.main")
    dummy_app = object()
    dummy_module.app = dummy_app
    monkeypatch.setitem(sys.modules, "crawler_center.api.main", dummy_module)
    return dummy_app


def test_main_uses_none_loop_on_windows(monkeypatch) -> None:
    dummy_app = _patch_dummy_app_module(monkeypatch)
    captured: dict[str, object] = {}

    monkeypatch.setattr(run_entry.sys, "platform", "win32", raising=False)
    monkeypatch.setattr(run_entry, "_configure_windows_asyncio_policy", lambda: None)

    def fake_run(app, **kwargs):
        captured["app"] = app
        captured.update(kwargs)

    monkeypatch.setattr(run_entry.uvicorn, "run", fake_run)

    run_entry.main()

    assert captured["app"] is dummy_app
    assert captured["loop"] == "none"
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8000


def test_main_uses_auto_loop_on_non_windows(monkeypatch) -> None:
    dummy_app = _patch_dummy_app_module(monkeypatch)
    captured: dict[str, object] = {}

    monkeypatch.setattr(run_entry.sys, "platform", "linux", raising=False)
    monkeypatch.setattr(run_entry, "_configure_windows_asyncio_policy", lambda: None)

    def fake_run(app, **kwargs):
        captured["app"] = app
        captured.update(kwargs)

    monkeypatch.setattr(run_entry.uvicorn, "run", fake_run)

    run_entry.main()

    assert captured["app"] is dummy_app
    assert captured["loop"] == "auto"
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8000
