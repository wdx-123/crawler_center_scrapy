"""Lanqiao 路由请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LanqiaoSolveStatsRequest(BaseModel):
    """做题统计查询请求。"""

    phone: str = Field(min_length=1)
    password: str = Field(min_length=1)
    sync_num: int = Field(ge=-1)


class LanqiaoStats(BaseModel):
    """蓝桥提交统计信息。"""

    total_passed: int = 0
    total_failed: int = 0


class LanqiaoProblem(BaseModel):
    """蓝桥通过题目条目。"""

    problem_name: str = ""
    problem_id: int
    created_at: str = ""
    is_passed: bool = True
