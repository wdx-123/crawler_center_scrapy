"""代理池服务与健康状态管理。

核心能力：
- 维护代理列表（同步替换、删除、快照）
- 按目标站点维度跟踪代理健康状态
- 在后台周期性主动探测代理可用性
- 为 Scrapy 中间件提供可用代理选择策略
"""

from __future__ import annotations

import asyncio
import random
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional
from urllib.parse import urlsplit

import requests


class TargetSite(str, Enum):
    """已支持的目标站点标识。"""

    LEETCODE = "leetcode"
    LUOGU = "luogu"
    LANQIAO = "lanqiao"


class ProxyStatus(str, Enum):
    """代理健康状态。"""

    OK = "OK"
    SUSPECT = "SUSPECT"
    DEAD = "DEAD"


@dataclass
class TargetHealth:
    """代理在单个目标站点上的健康统计。"""

    success_count: int = 0
    fail_count: int = 0
    consecutive_fail: int = 0
    avg_latency_ms: float = 0.0
    status: ProxyStatus = ProxyStatus.OK
    last_checked_at: float = 0.0


@dataclass
class ProxyRecord:
    """代理全局状态与多站点健康信息。"""

    proxy_url: str
    added_at: float
    last_checked_at: float = 0.0
    last_used_at: float = 0.0
    success_count: int = 0
    fail_count: int = 0
    consecutive_fail: int = 0
    avg_latency_ms: float = 0.0
    status: ProxyStatus = ProxyStatus.OK
    health_by_target: Dict[TargetSite, TargetHealth] = field(default_factory=dict)


class ProxyService:
    """线程安全的内存代理池服务。"""

    def __init__(self, probe_urls: Dict[str, str], user_agent: str, request_timeout_sec: int = 10) -> None:
        self._records: Dict[str, ProxyRecord] = {}
        self._lock = threading.RLock()
        self._probe_urls = {
            normalize_target_name(name): url for name, url in probe_urls.items() if normalize_target_name(name)
        }
        self._user_agent = user_agent
        self._request_timeout_sec = request_timeout_sec
        self._probe_task: Optional[asyncio.Task[None]] = None
        self._probe_stop_event = asyncio.Event()

    def _new_health(self) -> Dict[TargetSite, TargetHealth]:
        """初始化单代理的站点健康状态。"""
        return {
            TargetSite.LEETCODE: TargetHealth(),
            TargetSite.LUOGU: TargetHealth(),
            TargetSite.LANQIAO: TargetHealth(),
        }

    def _new_record(self, proxy_url: str) -> ProxyRecord:
        """创建新代理记录。"""
        now = time.time()
        return ProxyRecord(proxy_url=proxy_url, added_at=now, health_by_target=self._new_health())

    def sync_replace(self, proxy_urls: Iterable[str]) -> Dict[str, int]:
        """以新列表全量替换代理池。

        返回统计信息：total/added/updated/removed。
        """
        cleaned = [url.strip() for url in proxy_urls if str(url).strip()]
        deduped = list(dict.fromkeys(cleaned))

        with self._lock:
            old_set = set(self._records.keys())
            new_set = set(deduped)

            removed_urls = old_set - new_set
            for proxy_url in removed_urls:
                self._records.pop(proxy_url, None)

            added = 0
            updated = 0
            now = time.time()
            for proxy_url in deduped:
                if proxy_url in self._records:
                    updated += 1
                    self._records[proxy_url].last_checked_at = now
                else:
                    self._records[proxy_url] = self._new_record(proxy_url)
                    added += 1

            return {
                "total": len(self._records),
                "added": added,
                "updated": updated,
                "removed": len(removed_urls),
            }

    def remove(self, proxy_urls: Iterable[str]) -> Dict[str, int]:
        """删除指定代理并返回删除统计。"""
        removed = 0
        with self._lock:
            for proxy_url in proxy_urls:
                key = str(proxy_url).strip()
                if key and key in self._records:
                    self._records.pop(key, None)
                    removed += 1
            return {"total": len(self._records), "removed": removed}

    def has_any_proxy(self) -> bool:
        """判断代理池是否非空。"""
        with self._lock:
            return bool(self._records)

    def get_snapshot(self) -> List[Dict[str, object]]:
        """返回当前代理池快照（可用于调试或观测）。"""
        with self._lock:
            out: List[Dict[str, object]] = []
            for record in self._records.values():
                out.append(
                    {
                        "proxy_url": record.proxy_url,
                        "status": record.status.value,
                        "success_count": record.success_count,
                        "fail_count": record.fail_count,
                        "consecutive_fail": record.consecutive_fail,
                        "avg_latency_ms": round(record.avg_latency_ms, 2),
                        "last_checked_at": record.last_checked_at,
                        "last_used_at": record.last_used_at,
                        "health_by_target": {
                            target.value: {
                                "status": health.status.value,
                                "success_count": health.success_count,
                                "fail_count": health.fail_count,
                                "consecutive_fail": health.consecutive_fail,
                                "avg_latency_ms": round(health.avg_latency_ms, 2),
                            }
                            for target, health in record.health_by_target.items()
                        },
                    }
                )
            return out

    def list_proxies(
        self,
        global_status: str | ProxyStatus | None = None,
        target_site: str | TargetSite | None = None,
        target_status: str | ProxyStatus | None = None,
    ) -> Dict[str, object]:
        """按筛选条件返回代理列表视图与汇总信息。"""
        global_status_filter = _parse_proxy_status(global_status) if global_status is not None else None
        target_site_filter = _parse_target_site(target_site) if target_site is not None else None
        target_status_filter = _parse_proxy_status(target_status) if target_status is not None else None
        if target_status_filter and not target_site_filter:
            raise ValueError("target_site is required when target_status is provided")

        with self._lock:
            selected_records: List[ProxyRecord] = []
            for record in self._records.values():
                if global_status_filter and record.status != global_status_filter:
                    continue

                if target_site_filter and target_status_filter:
                    if record.health_by_target[target_site_filter].status != target_status_filter:
                        continue

                selected_records.append(record)

            selected_records.sort(key=lambda record: _list_sort_key(record, target_site_filter))

            items = [self._to_list_item(record) for record in selected_records]
            by_global_status = {
                ProxyStatus.OK.value: 0,
                ProxyStatus.SUSPECT.value: 0,
                ProxyStatus.DEAD.value: 0,
            }
            for record in selected_records:
                by_global_status[record.status.value] += 1

            return {
                "items": items,
                "summary": {
                    "total": len(items),
                    "by_global_status": by_global_status,
                    "applied_filters": {
                        "global_status": global_status_filter.value if global_status_filter else None,
                        "target_site": target_site_filter.value if target_site_filter else None,
                        "target_status": target_status_filter.value if target_status_filter else None,
                    },
                },
            }

    def _to_list_item(self, record: ProxyRecord) -> Dict[str, object]:
        """序列化单条代理记录为接口返回结构。"""
        return {
            "proxy_url": record.proxy_url,
            "ip_port": _extract_ip_port(record.proxy_url),
            "status": record.status.value,
            "status_label": _status_label(record.status),
            "success_count": record.success_count,
            "fail_count": record.fail_count,
            "consecutive_fail": record.consecutive_fail,
            "avg_latency_ms": round(record.avg_latency_ms, 2),
            "last_checked_at": record.last_checked_at,
            "last_used_at": record.last_used_at,
            "health_by_target": {
                target.value: {
                    "status": record.health_by_target[target].status.value,
                    "status_label": _status_label(record.health_by_target[target].status),
                    "success_count": record.health_by_target[target].success_count,
                    "fail_count": record.health_by_target[target].fail_count,
                    "consecutive_fail": record.health_by_target[target].consecutive_fail,
                    "avg_latency_ms": round(record.health_by_target[target].avg_latency_ms, 2),
                }
                for target in TargetSite
            },
        }

    def acquire_proxy(self, target: str) -> Optional[str]:
        """按健康度策略为目标站点选择一个代理。

        选择策略：
        - 过滤掉 `DEAD` 代理
        - 优先状态更健康、连续失败更少、延迟更低的代理
        """
        target_site = normalize_target(target)
        with self._lock:
            candidates = []
            for record in self._records.values():
                health = record.health_by_target[target_site]
                if health.status == ProxyStatus.DEAD:
                    continue
                candidates.append((record, health))

            if not candidates:
                return None

            random.shuffle(candidates)
            selected_record, selected_health = min(
                candidates,
                key=lambda pair: (
                    _status_priority(pair[1].status),
                    pair[1].consecutive_fail,
                    pair[1].avg_latency_ms if pair[1].avg_latency_ms > 0 else 999_999,
                    pair[1].fail_count - pair[1].success_count,
                ),
            )

            selected_record.last_used_at = time.time()
            selected_record.status = selected_health.status
            return selected_record.proxy_url

    def report_success(self, proxy_url: str, target: str, latency_ms: float) -> None:
        """上报一次成功访问，更新全局与站点级统计。"""
        target_site = normalize_target(target)
        with self._lock:
            record = self._records.get(proxy_url)
            if not record:
                return

            now = time.time()
            record.last_checked_at = now
            record.success_count += 1
            record.consecutive_fail = 0
            record.status = ProxyStatus.OK
            record.avg_latency_ms = _update_avg(record.avg_latency_ms, record.success_count, latency_ms)

            health = record.health_by_target[target_site]
            health.last_checked_at = now
            health.success_count += 1
            health.consecutive_fail = 0
            health.status = ProxyStatus.OK
            health.avg_latency_ms = _update_avg(health.avg_latency_ms, health.success_count, latency_ms)

    def report_failure(self, proxy_url: str, target: str) -> None:
        """上报一次失败访问，按连续失败次数更新健康状态。"""
        target_site = normalize_target(target)
        with self._lock:
            record = self._records.get(proxy_url)
            if not record:
                return

            now = time.time()
            record.last_checked_at = now
            record.fail_count += 1
            record.consecutive_fail += 1
            record.status = _derive_status(record.consecutive_fail)

            health = record.health_by_target[target_site]
            health.last_checked_at = now
            health.fail_count += 1
            health.consecutive_fail += 1
            health.status = _derive_status(health.consecutive_fail)

    async def start_probe_loop(self, interval_sec: int) -> None:
        """启动后台主动探测循环（幂等）。"""
        if self._probe_task and not self._probe_task.done():
            return
        self._probe_stop_event.clear()
        self._probe_task = asyncio.create_task(self._probe_loop(interval_sec))

    async def stop_probe_loop(self) -> None:
        """停止后台主动探测循环。"""
        if not self._probe_task:
            return
        self._probe_stop_event.set()
        self._probe_task.cancel()
        try:
            await self._probe_task
        except asyncio.CancelledError:
            pass
        self._probe_task = None

    async def probe_once(self) -> None:
        """对当前代理池执行一轮主动探测。"""
        snapshot = self.get_snapshot()
        for record in snapshot:
            proxy_url = str(record["proxy_url"])
            for target, probe_url in self._probe_urls.items():
                success, latency_ms = await asyncio.to_thread(self._probe_proxy, proxy_url, probe_url)
                if success:
                    self.report_success(proxy_url=proxy_url, target=target, latency_ms=latency_ms)
                else:
                    self.report_failure(proxy_url=proxy_url, target=target)

    async def _probe_loop(self, interval_sec: int) -> None:
        """后台探测循环主逻辑。"""
        while not self._probe_stop_event.is_set():
            try:
                await self.probe_once()
            except Exception:
                # Probing must not crash the service lifecycle.
                pass
            try:
                await asyncio.wait_for(self._probe_stop_event.wait(), timeout=max(interval_sec, 1))
            except asyncio.TimeoutError:
                continue

    def _probe_proxy(self, proxy_url: str, probe_url: str) -> tuple[bool, float]:
        """通过指定代理访问探测 URL，并返回(是否成功, 延迟毫秒)。"""
        started = time.perf_counter()
        try:
            response = requests.get(
                probe_url,
                timeout=self._request_timeout_sec,
                proxies={"http": proxy_url, "https": proxy_url},
                headers={"User-Agent": self._user_agent},
            )
            latency_ms = (time.perf_counter() - started) * 1000
            if response.status_code >= 400:
                return False, latency_ms
            return True, latency_ms
        except Exception:
            latency_ms = (time.perf_counter() - started) * 1000
            return False, latency_ms



def _derive_status(consecutive_fail: int) -> ProxyStatus:
    """根据连续失败次数推导健康状态。"""
    if consecutive_fail >= 3:
        return ProxyStatus.DEAD
    if consecutive_fail >= 2:
        return ProxyStatus.SUSPECT
    return ProxyStatus.OK


def _status_priority(status: ProxyStatus) -> int:
    """状态优先级：OK < SUSPECT < DEAD。"""
    if status == ProxyStatus.OK:
        return 0
    if status == ProxyStatus.SUSPECT:
        return 1
    return 2


def _status_label(status: ProxyStatus) -> str:
    """状态中文文案映射。"""
    if status == ProxyStatus.OK:
        return "好"
    if status == ProxyStatus.SUSPECT:
        return "中"
    return "坏"


def _latency_sort_value(latency_ms: float) -> float:
    """排序时将未知延迟（0）放在已知延迟之后。"""
    return latency_ms if latency_ms > 0 else 999_999


def _list_sort_key(record: ProxyRecord, target_site: TargetSite | None) -> tuple[int, int, float, str]:
    """列表接口排序键，支持按全局或单站点状态排序。"""
    if target_site:
        target_health = record.health_by_target[target_site]
        return (
            _status_priority(target_health.status),
            target_health.consecutive_fail,
            _latency_sort_value(target_health.avg_latency_ms),
            record.proxy_url,
        )

    return (
        _status_priority(record.status),
        record.consecutive_fail,
        _latency_sort_value(record.avg_latency_ms),
        record.proxy_url,
    )


def _parse_proxy_status(raw_status: str | ProxyStatus) -> ProxyStatus:
    """将输入严格转换为代理状态枚举。"""
    if isinstance(raw_status, ProxyStatus):
        return raw_status

    value = str(raw_status).strip().upper()
    try:
        return ProxyStatus(value)
    except ValueError as exc:
        raise ValueError(f"unsupported proxy status: {raw_status}") from exc


def _parse_target_site(raw_target: str | TargetSite) -> TargetSite:
    """将输入严格转换为目标站点枚举。"""
    if isinstance(raw_target, TargetSite):
        return raw_target

    value = str(raw_target).strip().lower()
    try:
        return TargetSite(value)
    except ValueError as exc:
        raise ValueError(f"unsupported target site: {raw_target}") from exc


def _extract_ip_port(proxy_url: str) -> str:
    """从代理 URL 中提取 `ip:port` 显示字段。"""
    value = str(proxy_url).strip()
    if "://" not in value:
        return value

    parsed = urlsplit(value)
    return parsed.netloc or value


def _update_avg(current_avg: float, count_after_increment: int, new_value: float) -> float:
    """增量更新平均值，避免保存完整历史样本。"""
    if count_after_increment <= 1:
        return float(new_value)
    previous_count = count_after_increment - 1
    return ((current_avg * previous_count) + float(new_value)) / count_after_increment


def normalize_target(raw_target: str | TargetSite | None) -> TargetSite:
    """将输入归一化为 `TargetSite` 枚举。"""
    if isinstance(raw_target, TargetSite):
        return raw_target

    normalized = normalize_target_name(raw_target)
    if normalized == TargetSite.LUOGU.value:
        return TargetSite.LUOGU
    if normalized == TargetSite.LANQIAO.value:
        return TargetSite.LANQIAO
    return TargetSite.LEETCODE


def normalize_target_name(raw_target: str | None) -> str:
    """将目标站点名称归一化为字符串标识，异常输入回退到 leetcode。"""
    if not raw_target:
        return TargetSite.LEETCODE.value
    lowered = str(raw_target).strip().lower()
    if lowered in {TargetSite.LEETCODE.value, TargetSite.LUOGU.value, TargetSite.LANQIAO.value}:
        return lowered
    return TargetSite.LEETCODE.value
