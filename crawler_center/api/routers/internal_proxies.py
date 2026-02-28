"""内部代理池管理路由。

该组接口仅面向内部系统调用，必须通过 `X-Internal-Token` 鉴权。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from crawler_center.api.dependencies import get_proxy_service
from crawler_center.api.schemas.common import OkResponse
from crawler_center.api.schemas.proxy import ProxyListQuery, ProxyRemoveRequest, ProxySyncRequest
from crawler_center.core.logging import log_event
from crawler_center.core.security import require_internal_token
from crawler_center.services.proxy_service import ProxyService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/proxies", tags=["internal-proxy"])


@router.get("", response_model=OkResponse, dependencies=[Depends(require_internal_token)])
async def list_proxies(
    request: Request,
    query: ProxyListQuery = Depends(),
    proxy_service: ProxyService = Depends(get_proxy_service),
) -> OkResponse:
    """查询代理池详情，支持全局/站点状态筛选。"""
    result = proxy_service.list_proxies(
        global_status=query.global_status,
        target_site=query.target_site,
        target_status=query.target_status,
    )
    log_event(
        logger,
        logging.INFO,
        "proxy_list",
        target="proxy_pool",
        endpoint="/internal/proxies",
        action="list",
        operator=request.headers.get("X-Request-ID", "unknown"),
        total=result["summary"]["total"],
        global_status=query.global_status,
        target_site=query.target_site,
        target_status=query.target_status,
    )
    return OkResponse(data=result)


@router.post("/sync", response_model=OkResponse, dependencies=[Depends(require_internal_token)])
async def sync_proxies(
    payload: ProxySyncRequest,
    request: Request,
    proxy_service: ProxyService = Depends(get_proxy_service),
) -> OkResponse:
    """用请求中的代理列表全量替换当前代理池。"""
    result = proxy_service.sync_replace(payload.proxies)
    log_event(
        logger,
        logging.INFO,
        "proxy_sync",
        target="proxy_pool",
        endpoint="/internal/proxies/sync",
        action="sync_replace",
        operator=request.headers.get("X-Request-ID", "unknown"),
        total=result["total"],
        added=result["added"],
        updated=result["updated"],
        removed=result["removed"],
    )
    return OkResponse(data=result)


@router.post("/remove", response_model=OkResponse, dependencies=[Depends(require_internal_token)])
async def remove_proxies(
    payload: ProxyRemoveRequest,
    request: Request,
    proxy_service: ProxyService = Depends(get_proxy_service),
) -> OkResponse:
    """从代理池中移除指定代理。"""
    result = proxy_service.remove(payload.proxy_urls)
    log_event(
        logger,
        logging.INFO,
        "proxy_remove",
        target="proxy_pool",
        endpoint="/internal/proxies/remove",
        action="remove",
        operator=request.headers.get("X-Request-ID", "unknown"),
        total=result["total"],
        removed=result["removed"],
    )
    return OkResponse(data=result)
