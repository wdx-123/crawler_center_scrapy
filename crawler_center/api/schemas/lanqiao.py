"""Lanqiao 路由请求/响应模型。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class LanqiaoLoginRequest(BaseModel):
    """登录请求参数。"""

    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class LanqiaoLoginResponse(BaseModel):
    """登录响应数据。"""

    ok: bool = True
    cookie_header: str = Field(..., description="cookie header string")
    cookies: Optional[Dict[str, str]] = Field(default=None)
    message: Optional[str] = None


class LanqiaoSolveStatsRequest(BaseModel):
    """做题统计查询请求。"""

    cookie_header: Optional[str] = Field(default=None)
    user_id: Optional[str] = Field(default=None)


class LanqiaoSolveStatsResponse(BaseModel):
    """做题统计查询响应。"""

    ok: bool = True
    solved_count: Optional[int] = None
    extra: Dict[str, Any] = Field(default_factory=dict)
    message: Optional[str] = None
