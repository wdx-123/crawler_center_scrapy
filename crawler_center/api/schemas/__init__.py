"""API 契约模型聚合导出。

该模块作为外部引用的稳定入口，减少调用方对具体 schema 文件路径的耦合。
"""

from .common import ErrorResponse, OkResponse
from .lanqiao import (
    LanqiaoLoginRequest,
    LanqiaoLoginResponse,
    LanqiaoSolveStatsRequest,
    LanqiaoSolveStatsResponse,
)
from .leetcode import LeetCodeUserRequest
from .luogu import LuoguUserRequest
from .proxy import ProxyRemoveRequest, ProxySyncRequest

__all__ = [
    "ErrorResponse",
    "OkResponse",
    "LeetCodeUserRequest",
    "LuoguUserRequest",
    "LanqiaoLoginRequest",
    "LanqiaoLoginResponse",
    "LanqiaoSolveStatsRequest",
    "LanqiaoSolveStatsResponse",
    "ProxySyncRequest",
    "ProxyRemoveRequest",
]
