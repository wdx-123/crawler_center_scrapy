"""Span 推送后端：Protocol 定义 + RedisTraceBackend 实现。

RedisTraceBackend 通过 asyncio.Queue 做内存缓冲，后台协程定时批量
XADD 到共享 Redis Stream，由 Go 侧 consumer 消费入库。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, Protocol, runtime_checkable

from redis.asyncio import Redis

from crawler_center.observability.models import Span

logger = logging.getLogger(__name__)


@runtime_checkable
class TraceBackend(Protocol):
    """Span 推送后端协议，便于扩展（如替换为 OTLP exporter）。"""

    async def record_span(self, span: Span) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...


class NoopTraceBackend:
    """空实现，observability 关闭或 Redis 不可用时使用。"""

    async def record_span(self, span: Span) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class RedisTraceBackend:
    """基于 Redis Stream 的 Span 推送后端。

    架构：asyncio.Queue (内存缓冲) -> 后台 flush 协程 -> XADD traces:stream
    """

    def __init__(
        self,
        redis_client: Redis,
        *,
        stream_key: str = "traces:stream",
        stream_maxlen: int = 10000,
        queue_size: int = 2048,
        flush_interval_sec: float = 0.5,
        flush_batch_size: int = 50,
        max_payload_bytes: int = 4096,
    ) -> None:
        self._redis = redis_client
        self._stream_key = stream_key
        self._stream_maxlen = stream_maxlen
        self._queue: asyncio.Queue[Span] = asyncio.Queue(maxsize=queue_size)
        self._flush_interval = flush_interval_sec
        self._flush_batch = flush_batch_size
        self._max_payload = max_payload_bytes
        self._task: Optional[asyncio.Task[None]] = None
        self._stopped = False

    async def record_span(self, span: Span) -> None:
        """将 Span 推入内存队列，队列满时丢弃并计数。"""
        if self._stopped:
            return
        try:
            self._queue.put_nowait(span)
        except asyncio.QueueFull:
            logger.debug("trace queue full, span dropped: %s", span.name)

    async def start(self) -> None:
        """启动后台 flush 协程。"""
        if self._task is not None:
            return
        self._stopped = False
        self._task = asyncio.create_task(self._run_flusher())

    async def stop(self) -> None:
        """停止后台协程并 flush 剩余 Span。"""
        self._stopped = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._flush_remaining()

    async def _run_flusher(self) -> None:
        """后台循环：定时 + 批量触发 flush。"""
        buffer: list[Span] = []
        while True:
            try:
                span = await asyncio.wait_for(
                    self._queue.get(), timeout=self._flush_interval
                )
                buffer.append(span)
                if len(buffer) >= self._flush_batch:
                    await self._flush(buffer)
                    buffer = []
            except asyncio.TimeoutError:
                if buffer:
                    await self._flush(buffer)
                    buffer = []
            except asyncio.CancelledError:
                if buffer:
                    await self._flush(buffer)
                raise

    async def _flush_remaining(self) -> None:
        """排空队列中剩余的 Span。"""
        buffer: list[Span] = []
        while not self._queue.empty():
            try:
                buffer.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if buffer:
            await self._flush(buffer)

    async def _flush(self, spans: list[Span]) -> None:
        """批量 XADD 到 Redis Stream。"""
        if not spans:
            return
        pipe = self._redis.pipeline(transaction=False)
        for span in spans:
            payload = span.to_json()
            if self._max_payload > 0 and len(payload) > self._max_payload:
                payload = payload[: self._max_payload]
            pipe.xadd(
                self._stream_key,
                {"payload": payload},
                maxlen=self._stream_maxlen,
                approximate=True,
            )
        try:
            await pipe.execute()
        except Exception:
            logger.warning(
                "flush %d spans to redis stream failed", len(spans), exc_info=True
            )
