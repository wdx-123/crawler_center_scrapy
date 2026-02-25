"""代理池管理请求模型。"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class ProxySyncRequest(BaseModel):
    """代理池全量同步请求。"""

    proxies: List[str] = Field(default_factory=list)


class ProxyRemoveRequest(BaseModel):
    """代理池删除请求。"""

    proxy_urls: List[str] = Field(default_factory=list)
