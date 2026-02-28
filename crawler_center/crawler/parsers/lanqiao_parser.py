"""Lanqiao 解析器（纯函数）。"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


def parse_submission_stats(submissions: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    """统计原始提交中的通过与失败次数。"""
    total_passed = 0
    total_failed = 0
    for row in submissions:
        if bool(row.get("is_passed")):
            total_passed += 1
        else:
            total_failed += 1
    return {"total_passed": total_passed, "total_failed": total_failed}


def parse_passed_problems(submissions: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """筛选通过题并按 problem_id 去重，保留最早 created_at 记录。"""
    deduped: Dict[int, Dict[str, Any]] = {}
    for row in submissions:
        if not bool(row.get("is_passed")):
            continue

        problem_id = _parse_problem_id(row.get("problem_id"))
        if problem_id is None:
            continue

        candidate = {
            "problem_name": str(row.get("problem_name") or ""),
            "problem_id": problem_id,
            "created_at": str(row.get("created_at") or ""),
            "is_passed": True,
        }
        existing = deduped.get(problem_id)
        if existing is None or _is_earlier(candidate["created_at"], existing["created_at"]):
            deduped[problem_id] = candidate

    return list(deduped.values())


def build_solve_stats_payload(submissions: List[Dict[str, Any]], sync_num: int) -> Dict[str, Any]:
    """按 sync_num 输出约定结构。"""
    stats = parse_submission_stats(submissions)
    problems = parse_passed_problems(submissions)
    if sync_num == -1:
        return {"stats": stats}
    if sync_num == 0:
        return {"stats": stats, "problems": problems}
    return {"problems": problems}


def _parse_problem_id(raw_value: Any) -> int | None:
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _is_earlier(candidate: str, existing: str) -> bool:
    if not candidate:
        return False
    if not existing:
        return True
    return candidate < existing
