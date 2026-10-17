"""广播 hub：内存 pub/sub（连接集合 + 广播），五类事件推送给 WebSocket。

_Sender Protocol 解耦真实 WebSocket，便于单测；死连接（send_json 抛异常）即时剔除，
广播不抛出。
"""

import asyncio
from typing import Any, Protocol


class _Sender(Protocol):
    """WebSocket 最小接口：accept 建立连接，send_json 推送 JSON。"""

    async def accept(self) -> None: ...
    async def send_json(self, data: Any) -> None: ...


class StreamHub:
    """连接集合 + 广播；广播时遍历集合快照，send 抛异常的连接即时剔除。"""

    def __init__(self) -> None:
        self._connections: set[_Sender] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: _Sender) -> None:
        """accept 后加入连接集合。"""
        await ws.accept()
        self._connections.add(ws)

    def disconnect(self, ws: _Sender) -> None:
        """从连接集合移除（幂等）。"""
        self._connections.discard(ws)

    async def broadcast(self, event: dict[str, Any]) -> None:
        """向所有连接推送事件；死连接即时剔除且不抛出。"""
        async with self._lock:
            for ws in list(self._connections):
                try:
                    await ws.send_json(event)
                except Exception:
                    self._connections.discard(ws)
