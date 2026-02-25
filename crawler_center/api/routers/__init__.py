"""路由聚合导出。

统一在此导出路由对象，供 `api.main` 一次性挂载，避免入口文件直接依赖具体路由模块实现细节。
"""

from .healthz import router as healthz_router
from .internal_proxies import router as internal_proxies_router
from .lanqiao import router as lanqiao_router
from .leetcode import router as leetcode_router
from .luogu import router as luogu_router

__all__ = [
    "healthz_router",
    "leetcode_router",
    "luogu_router",
    "lanqiao_router",
    "internal_proxies_router",
]
