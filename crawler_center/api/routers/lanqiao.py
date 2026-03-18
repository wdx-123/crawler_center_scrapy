"""Lanqiao 业务路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from crawler_center.api.dependencies import get_lanqiao_service
from crawler_center.api.schemas.common import ErrorResponse, OkResponse
from crawler_center.api.schemas.lanqiao import LanqiaoSolveStatsRequest
from crawler_center.services.lanqiao_service import LanqiaoService

router = APIRouter(prefix="/v2/lanqiao", tags=["lanqiao"])


@router.post(
    "/solve_stats",
    response_model=OkResponse,
    responses={
        401: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def solve_stats(
    payload: LanqiaoSolveStatsRequest,
    service: LanqiaoService = Depends(get_lanqiao_service),
) -> OkResponse:
    """登录蓝桥并拉取做题统计。"""
    data = await service.solve_stats(phone=payload.phone, password=payload.password, sync_num=payload.sync_num)
    return OkResponse(data=data)
