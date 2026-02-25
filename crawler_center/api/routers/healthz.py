"""健康检查路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from crawler_center.api.dependencies import get_settings
from crawler_center.api.schemas.common import OkResponse
from crawler_center.core.config import AppSettings

router = APIRouter(prefix="/v2", tags=["healthz"])


@router.get("/healthz", response_model=OkResponse)
async def healthz(settings: AppSettings = Depends(get_settings)) -> OkResponse:
    """返回服务可用状态与版本号。"""
    return OkResponse(data={"status": "ok", "version": settings.api_version})
