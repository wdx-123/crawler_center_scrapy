from __future__ import annotations

import pytest

from crawler_center.core.errors import UpstreamRequestError
from crawler_center.services.lanqiao_service import LanqiaoService
from tests.conftest import build_test_settings


class _DummyRunner:
    def __init__(self, items):
        self._items = items

    async def run(self, spider_cls, **kwargs):  # noqa: ANN001
        return list(self._items)


@pytest.mark.asyncio
async def test_lanqiao_service_raises_upstream_error_from_item() -> None:
    runner = _DummyRunner(items=[{"_error": "bad gateway", "_stage": "login"}])
    service = LanqiaoService(runner=runner, settings=build_test_settings())  # type: ignore[arg-type]

    with pytest.raises(UpstreamRequestError) as exc_info:
        await service.solve_stats(phone="13800000000", password="pwd", sync_num=0)

    assert "[login]" in str(exc_info.value)


@pytest.mark.asyncio
async def test_lanqiao_service_mode_outputs() -> None:
    items = [
        {"problem_name": "A", "problem_id": 101, "created_at": "2025-01-02T00:00:00+08:00", "is_passed": True},
        {"problem_name": "A-old", "problem_id": 101, "created_at": "2025-01-01T00:00:00+08:00", "is_passed": True},
        {"problem_name": "B", "problem_id": 102, "created_at": "2025-01-03T00:00:00+08:00", "is_passed": False},
    ]
    runner = _DummyRunner(items=items)
    service = LanqiaoService(runner=runner, settings=build_test_settings())  # type: ignore[arg-type]

    stats_only = await service.solve_stats(phone="13800000000", password="pwd", sync_num=-1)
    full_sync = await service.solve_stats(phone="13800000000", password="pwd", sync_num=0)
    incremental = await service.solve_stats(phone="13800000000", password="pwd", sync_num=5)

    assert stats_only == {"stats": {"total_passed": 2, "total_failed": 1}}
    assert full_sync["stats"] == {"total_passed": 2, "total_failed": 1}
    assert full_sync["problems"] == [
        {"problem_name": "A-old", "problem_id": 101, "created_at": "2025-01-01T00:00:00+08:00", "is_passed": True}
    ]
    assert incremental == {
        "problems": [
            {"problem_name": "A-old", "problem_id": 101, "created_at": "2025-01-01T00:00:00+08:00", "is_passed": True}
        ]
    }


@pytest.mark.asyncio
async def test_lanqiao_service_empty_items_is_stable() -> None:
    runner = _DummyRunner(items=[])
    service = LanqiaoService(runner=runner, settings=build_test_settings())  # type: ignore[arg-type]

    assert await service.solve_stats(phone="13800000000", password="pwd", sync_num=-1) == {
        "stats": {"total_passed": 0, "total_failed": 0}
    }
    assert await service.solve_stats(phone="13800000000", password="pwd", sync_num=0) == {
        "stats": {"total_passed": 0, "total_failed": 0},
        "problems": [],
    }
    assert await service.solve_stats(phone="13800000000", password="pwd", sync_num=3) == {"problems": []}
