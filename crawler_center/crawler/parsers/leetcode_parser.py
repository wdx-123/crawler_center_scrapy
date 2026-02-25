"""LeetCode 解析器（纯函数）。

职责边界：
- 接收 spider 已拿到的 HTML/JSON 数据。
- 输出业务可消费的稳定 dict/list 结构。
- 不抛业务异常；异常语义通过返回值（如 ``_error``）向上游传递。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from lxml import html


def parse_profile_meta_html(page_html: str, status_code: int, final_url: str) -> Dict[str, Any]:
    """解析用户主页 HTML 元信息。

    参数：
    - ``page_html``: 页面原始 HTML 文本。
    - ``status_code``: HTTP 状态码。
    - ``final_url``: 最终落地 URL（包含可能的跳转结果）。

    返回：
    - 用户不存在或不可访问时，返回 ``exists=False`` 的稳定结构。
    - 正常时返回 ``og_title`` / ``og_description`` 等元信息字段。
    """
    exists = status_code < 400 and status_code != 404
    if not exists:
        return {"exists": False, "reason": f"HTTP {status_code}", "url_final": final_url}

    doc = html.fromstring(page_html)
    og_title = doc.xpath("//meta[@property='og:title']/@content")
    og_desc = doc.xpath("//meta[@property='og:description']/@content")
    return {
        "exists": True,
        "url_final": final_url,
        "og_title": og_title[0] if og_title else "",
        "og_description": og_desc[0] if og_desc else "",
    }


def parse_graphql_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """解析 GraphQL 响应根节点。

    约定：
    - 若响应携带 ``errors``，返回 ``{"_error": ...}``，由 service 统一提升为异常。
    - 若 ``data`` 非 dict，返回空 dict，避免上层出现类型错误。
    """
    errors = raw.get("errors") if isinstance(raw, dict) else None
    if errors:
        return {"_error": f"GraphQL errors: {json.dumps(errors, ensure_ascii=False)}"}
    data = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(data, dict):
        return {}
    return data


def parse_recent_ac_data(payload_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 GraphQL data 中提取最近 AC 列表。

    输出字段：
    - ``title``: 题目名称（优先中文名 ``translatedTitle``）。
    - ``slug``: 题目标识。
    - ``timestamp``: 秒级时间戳（int）。

    容错策略：
    - 缺失关键字段或时间戳非法的记录会被静默丢弃，保证输出质量。
    """
    rows = payload_data.get("recentACSubmissions", []) if isinstance(payload_data, dict) else []
    out: List[Dict[str, Any]] = []

    for row in rows:
        question = row.get("question") or {}
        title = question.get("translatedTitle") or question.get("title") or ""
        slug = question.get("titleSlug") or ""
        submit_time = row.get("submitTime")

        try:
            timestamp = int(submit_time)
        except (TypeError, ValueError):
            timestamp = 0

        if title and slug and timestamp:
            out.append(
                {
                    "title": title,
                    "slug": slug,
                    "timestamp": timestamp,
                }
            )

    return out


def parse_submit_stats_data(payload_data: Dict[str, Any]) -> Dict[str, Any]:
    """解析提交统计数据。

    当前策略：
    - 直接透传 dict（由上层 service 决定最终 API 映射）。
    - 非 dict 输入时回退空 dict。
    """
    return payload_data if isinstance(payload_data, dict) else {}


def parse_public_profile_data(payload_data: Dict[str, Any]) -> Dict[str, Any]:
    """解析公开资料字段并返回稳定结构。

    返回字段：
    - ``userSlug``
    - ``realName``
    - ``userAvatar``
    """
    root = payload_data.get("userProfilePublicProfile") if isinstance(payload_data, dict) else None
    profile = root.get("profile") if isinstance(root, dict) else {}
    return {
        "userSlug": profile.get("userSlug") or "",
        "realName": profile.get("realName") or "",
        "userAvatar": profile.get("userAvatar") or "",
    }
