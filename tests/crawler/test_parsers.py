from __future__ import annotations

import json
from pathlib import Path

from crawler_center.crawler.parsers.leetcode_parser import (
    parse_graphql_payload,
    parse_profile_meta_html,
    parse_public_profile_data,
    parse_recent_ac_data,
)
from crawler_center.crawler.parsers.lanqiao_parser import (
    build_solve_stats_payload,
    parse_passed_problems,
    parse_submission_stats,
)
from crawler_center.crawler.parsers.luogu_parser import parse_luogu_practice_context


def test_leetcode_profile_meta_parser_snapshot() -> None:
    html_text = Path("tests/fixtures/snapshots/leetcode_profile_meta.html").read_text(encoding="utf-8")
    parsed = parse_profile_meta_html(html_text, status_code=200, final_url="https://leetcode.cn/u/demo/")

    assert parsed == {
        "exists": True,
        "url_final": "https://leetcode.cn/u/demo/",
        "og_title": "leetcode profile",
        "og_description": "public profile desc",
    }


def test_leetcode_recent_ac_parser_snapshot() -> None:
    raw = json.loads(Path("tests/fixtures/snapshots/leetcode_recent_ac.json").read_text(encoding="utf-8-sig"))
    data = parse_graphql_payload(raw)
    rows = parse_recent_ac_data(data)

    assert rows == [
        {"title": "Two Sum CN", "slug": "two-sum", "timestamp": 1700000000},
        {"title": "Add Two Numbers", "slug": "add-two-numbers", "timestamp": 1700000100},
    ]


def test_public_profile_parser() -> None:
    payload = {
        "userProfilePublicProfile": {
            "profile": {
                "userSlug": "demo",
                "realName": "Demo",
                "userAvatar": "https://avatar",
            }
        }
    }

    assert parse_public_profile_data(payload) == {
        "userSlug": "demo",
        "realName": "Demo",
        "userAvatar": "https://avatar",
    }


def test_luogu_parser_snapshot() -> None:
    raw = json.loads(Path("tests/fixtures/snapshots/luogu_context.json").read_text(encoding="utf-8-sig"))
    parsed = parse_luogu_practice_context(raw)

    assert parsed["user"] == {"uid": 1, "name": "demo", "avatar": "https://img.example/avatar.png"}
    assert parsed["passed_count"] == 2


def test_lanqiao_submission_stats_and_dedup() -> None:
    rows = [
        {
            "problem_name": "A",
            "problem_id": 208,
            "created_at": "2025-02-10T10:24:00.517000+08:00",
            "is_passed": True,
        },
        {
            "problem_name": "A-older",
            "problem_id": 208,
            "created_at": "2025-02-09T10:24:00.517000+08:00",
            "is_passed": True,
        },
        {
            "problem_name": "B",
            "problem_id": 300,
            "created_at": "2025-02-11T10:24:00.517000+08:00",
            "is_passed": False,
        },
    ]

    assert parse_submission_stats(rows) == {"total_passed": 2, "total_failed": 1}
    assert parse_passed_problems(rows) == [
        {
            "problem_name": "A-older",
            "problem_id": 208,
            "created_at": "2025-02-09T10:24:00.517000+08:00",
            "is_passed": True,
        }
    ]


def test_lanqiao_payload_modes_and_defaults() -> None:
    rows = [
        {"problem_name": "x", "problem_id": "12", "created_at": "", "is_passed": True},
        {"problem_name": "y", "problem_id": None, "created_at": "2025-01-01T00:00:00+08:00", "is_passed": True},
        {"problem_name": "z", "problem_id": 99, "created_at": "2025-01-02T00:00:00+08:00", "is_passed": False},
    ]

    stats_only = build_solve_stats_payload(rows, sync_num=-1)
    full_sync = build_solve_stats_payload(rows, sync_num=0)
    incremental = build_solve_stats_payload(rows, sync_num=5)

    assert stats_only == {"stats": {"total_passed": 2, "total_failed": 1}}
    assert full_sync["stats"] == {"total_passed": 2, "total_failed": 1}
    assert full_sync["problems"] == [{"problem_name": "x", "problem_id": 12, "created_at": "", "is_passed": True}]
    assert incremental == {"problems": [{"problem_name": "x", "problem_id": 12, "created_at": "", "is_passed": True}]}
