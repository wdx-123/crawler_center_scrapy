"""代理池管理请求模型。"""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field, model_validator


class ProxySyncRequest(BaseModel):
    """代理池全量同步请求。"""

    proxies: List[str] = Field(default_factory=list)


class ProxyRemoveRequest(BaseModel):
    """代理池删除请求。"""

    proxy_urls: List[str] = Field(default_factory=list)


class ProxyListQuery(BaseModel):
    """代理池列表查询参数。"""

    global_status: Literal["OK", "SUSPECT", "DEAD"] | None = Field(default=None)
    target_site: Literal["leetcode", "luogu", "lanqiao"] | None = Field(default=None)
    target_status: Literal["OK", "SUSPECT", "DEAD"] | None = Field(default=None)

    @model_validator(mode="after")
    def ensure_target_site_for_target_status(self) -> "ProxyListQuery":
        """target_status 生效前必须显式指定 target_site。"""
        if self.target_status and not self.target_site:
            raise ValueError("target_site is required when target_status is provided")
        return self
