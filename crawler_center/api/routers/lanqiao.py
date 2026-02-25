"""Lanqiao 路由（当前为骨架实现）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from crawler_center.api.dependencies import get_lanqiao_service
from crawler_center.api.schemas.lanqiao import (
    LanqiaoLoginRequest,
    LanqiaoLoginResponse,
    LanqiaoSolveStatsRequest,
    LanqiaoSolveStatsResponse,
)
from crawler_center.services.lanqiao_service import LanqiaoService

router = APIRouter(prefix="/v2/lanqiao", tags=["lanqiao"])


@router.post("/login", response_model=LanqiaoLoginResponse)
async def login(payload: LanqiaoLoginRequest, service: LanqiaoService = Depends(get_lanqiao_service)) -> LanqiaoLoginResponse:
    """登录并返回 cookie 信息。

    该能力目前未实现，服务层会抛出 `NotImplementedError`，此处映射为 501。
    """
    try:
        cookie_info = await service.login(username=payload.username, password=payload.password)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    return LanqiaoLoginResponse(
        ok=True,
        cookie_header=cookie_info.cookie_header,
        cookies=cookie_info.cookies,
    )


@router.post("/solve_stats", response_model=LanqiaoSolveStatsResponse)
async def solve_stats(
    payload: LanqiaoSolveStatsRequest,
    service: LanqiaoService = Depends(get_lanqiao_service),
) -> LanqiaoSolveStatsResponse:
    """获取蓝桥做题统计。

    该能力目前未实现，服务层会抛出 `NotImplementedError`，此处映射为 501。
    """
    try:
        data = await service.solve_stats(cookie_header=payload.cookie_header, user_id=payload.user_id)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    return LanqiaoSolveStatsResponse(ok=True, solved_count=data.get("solved_count"), extra=data)
