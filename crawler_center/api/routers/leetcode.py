"""LeetCode 业务路由。

该路由层只做协议转换与依赖注入，不承载业务逻辑。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from crawler_center.api.dependencies import get_leetcode_service
from crawler_center.api.schemas.common import ErrorResponse, OkResponse
from crawler_center.api.schemas.leetcode import LeetCodeUserRequest
from crawler_center.services.leetcode_service import LeetCodeService

router = APIRouter(prefix="/v2/leetcode", tags=["leetcode"])


@router.post(
    "/profile_meta",
    response_model=OkResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def profile_meta(payload: LeetCodeUserRequest, service: LeetCodeService = Depends(get_leetcode_service)) -> OkResponse:
    """抓取用户主页元信息（存在性、标题、描述等）。"""
    meta = await service.profile_meta(username=payload.username, sleep_sec=payload.sleep_sec)
    return OkResponse(data={"meta": meta})


@router.post(
    "/recent_ac",
    response_model=OkResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def recent_ac(payload: LeetCodeUserRequest, service: LeetCodeService = Depends(get_leetcode_service)) -> OkResponse:
    """抓取用户最近 AC 记录。"""
    items = await service.recent_ac(username=payload.username, sleep_sec=payload.sleep_sec)
    return OkResponse(data={"recent_accepted": items})


@router.post(
    "/submit_stats",
    response_model=OkResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def submit_stats(payload: LeetCodeUserRequest, service: LeetCodeService = Depends(get_leetcode_service)) -> OkResponse:
    """抓取用户提交统计信息。"""
    stats = await service.submit_stats(username=payload.username, sleep_sec=payload.sleep_sec)
    return OkResponse(data={"stats": stats})


@router.post(
    "/public_profile",
    response_model=OkResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def public_profile(payload: LeetCodeUserRequest, service: LeetCodeService = Depends(get_leetcode_service)) -> OkResponse:
    """抓取用户公开资料。"""
    profile = await service.public_profile(username=payload.username, sleep_sec=payload.sleep_sec)
    return OkResponse(data={"profile": profile})


@router.post(
    "/crawl",
    response_model=OkResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def crawl(payload: LeetCodeUserRequest, service: LeetCodeService = Depends(get_leetcode_service)) -> OkResponse:
    """聚合抓取用户公开信息（meta + recent_ac + stats）。"""
    data = await service.crawl(username=payload.username, sleep_sec=payload.sleep_sec)
    return OkResponse(data=data)
