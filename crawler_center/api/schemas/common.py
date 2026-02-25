"""通用响应模型定义。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class OkResponse(BaseModel):
    """统一成功响应结构。"""

    ok: bool = True
    data: Dict[str, Any]


class ErrorResponse(BaseModel):
    """统一错误响应结构。"""

    ok: bool = False
    error: str
    code: Optional[str] = Field(default=None, description="machine readable error code")
