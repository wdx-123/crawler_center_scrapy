"""Luogu 路由请求模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LuoguUserRequest(BaseModel):
    """Luogu 用户抓取请求参数。"""

    uid: int = Field(gt=0)
    sleep_sec: float = Field(default=0.8, ge=0.0, le=10.0)
