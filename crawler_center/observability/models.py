"""Span 数据模型，精确匹配 Go 侧 pkg/observability/trace/types.go 的 JSON schema。

Python 侧构建的 Span 经 to_json() 序列化后推入 Redis Stream，
Go 侧 Backend.runConsumer 反序列化后直接入库，因此字段名和时间格式必须严格一致。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

STATUS_OK = "ok"
STATUS_ERROR = "error"

_ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _format_time(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime(_ISO_FORMAT)


@dataclass
class Span:
    span_id: str = ""
    parent_span_id: str = ""
    trace_id: str = ""
    request_id: str = ""

    service: str = ""
    stage: str = ""
    name: str = ""
    kind: str = ""
    status: str = STATUS_OK

    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    duration_ms: int = 0

    error_code: str = ""
    message: str = ""
    tags: Dict[str, str] = field(default_factory=dict)

    request_snippet: str = ""
    response_snippet: str = ""
    error_stack: str = ""
    error_detail_json: str = ""

    def finish(self, *, status: str = STATUS_OK, error_code: str = "", message: str = "") -> None:
        """标记 Span 结束，自动计算 duration_ms。"""
        self.end_at = _utcnow()
        self.status = status
        if error_code:
            self.error_code = error_code
        if message:
            self.message = message
        if self.start_at and self.end_at:
            delta = self.end_at - self.start_at
            self.duration_ms = max(0, int(delta.total_seconds() * 1000))

    def to_json(self) -> str:
        """序列化为与 Go Span JSON 完全兼容的字符串。"""
        d = asdict(self)
        d["start_at"] = _format_time(self.start_at)
        d["end_at"] = _format_time(self.end_at)
        return json.dumps(d, ensure_ascii=False, separators=(",", ":"))
