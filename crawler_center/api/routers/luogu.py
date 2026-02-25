"""Luogu 业务路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from crawler_center.api.dependencies import get_luogu_service
from crawler_center.api.schemas.common import ErrorResponse, OkResponse
from crawler_center.api.schemas.luogu import LuoguUserRequest
from crawler_center.services.luogu_service import LuoguService

router = APIRouter(prefix="/v2/luogu", tags=["luogu"])


@router.post(
    "/practice",
    response_model=OkResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def practice(payload: LuoguUserRequest, service: LuoguService = Depends(get_luogu_service)) -> OkResponse:
    """抓取用户练题数据（通过列表与计数）。"""
    data = await service.practice(uid=payload.uid, sleep_sec=payload.sleep_sec)
    return OkResponse(data=data)
