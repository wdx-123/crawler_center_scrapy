"""LeetCode 路由请求模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LeetCodeUserRequest(BaseModel):
    """LeetCode 用户抓取请求参数。"""

    username: str = Field(min_length=1)
    sleep_sec: float = Field(default=0.8, ge=0.0, le=10.0)
