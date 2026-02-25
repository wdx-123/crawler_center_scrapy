"""Luogu 解析器（纯函数）。

职责：
- 从 HTML 中提取 ``lentille-context`` JSON。
- 将上下文转换为稳定业务结构（user/passed/passed_count）。
"""

from __future__ import annotations

import json
from typing import Any, Dict

from lxml import html


def extract_lentille_context(raw_html: str) -> Dict[str, Any]:
    """从页面 HTML 中提取 ``<script id="lentille-context">`` JSON。

    返回：
    - 找不到节点或节点为空时返回空 dict。
    - 找到时返回反序列化后的 dict。

    注意：
    - JSON 解码异常由调用方（spider）处理并映射为 ``_error``。
    """
    doc = html.fromstring(raw_html)
    node = doc.xpath("//script[@id='lentille-context']/text()")
    if not node or not node[0].strip():
        return {}
    return json.loads(node[0])


def parse_luogu_practice_context(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """解析 Luogu 练题上下文为稳定返回结构。

    输出格式：
    - ``user``: ``{uid, name, avatar}``
    - ``passed``: 通过题目列表（每项含 pid/title/difficulty/type）
    - ``passed_count``: ``passed`` 长度

    设计考虑：
    - 对字段缺失做默认值填充，减少上层判空逻辑。
    """
    data = ctx.get("data") or {}
    user = data.get("user") or {}
    passed = data.get("passed") or []

    user_info = {
        "uid": user.get("uid"),
        "name": user.get("name") or "",
        "avatar": user.get("avatar") or "",
    }

    passed_rows = []
    for row in passed:
        passed_rows.append(
            {
                "pid": row.get("pid", ""),
                "title": row.get("title", ""),
                "difficulty": row.get("difficulty"),
                "type": row.get("type", ""),
            }
        )

    return {
        "user": user_info,
        "passed": passed_rows,
        "passed_count": len(passed_rows),
    }
