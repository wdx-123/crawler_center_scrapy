"""内部接口鉴权依赖。"""

from __future__ import annotations

from fastapi import Header, HTTPException, Request

from .errors import InternalTokenUnavailableError


def require_internal_token(
    request: Request,
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> None:
    """校验内部路由 token。

    规则：
    - 未配置 `INTERNAL_TOKEN` 时返回 503（服务未就绪）
    - 请求头 token 不匹配时返回 401
    """
    token = getattr(request.app.state.settings, "internal_token", None)
    if not token:
        exc = InternalTokenUnavailableError()
        raise HTTPException(status_code=503, detail=str(exc))
    if x_internal_token != token:
        raise HTTPException(status_code=401, detail="invalid internal token")
