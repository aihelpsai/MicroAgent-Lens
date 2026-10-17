"""广播 hub StreamHub 测试。"""

import asyncio
from typing import Any

from lens.server.stream import StreamHub


class _FakeSender:
    """记录 send_json 收到的 payload；可配置发送抛异常模拟死连接。"""

    def __init__(self, fail_send: bool = False) -> None:
        self.sent: list[Any] = []
        self.fail_send = fail_send
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data: Any) -> None:
        if self.fail_send:
            raise RuntimeError("connection lost")
        self.sent.append(data)


async def _case_connect_accepts() -> bool:
    hub = StreamHub()
    ws = _FakeSender()
    await hub.connect(ws)
    return ws.accepted


def test_connect_accepts() -> None:
    assert asyncio.run(_case_connect_accepts()) is True


async def _case_broadcast_reaches_connected() -> tuple[list[Any], list[Any]]:
    hub = StreamHub()
    a = _FakeSender()
    b = _FakeSender()
    await hub.connect(a)
    await hub.connect(b)
    event = {"type": "node_added", "session_id": "s1", "node": {"node_id": "n1"}}
    await hub.broadcast(event)
    return a.sent, b.sent


def test_broadcast_reaches_connected() -> None:
    """广播到达所有已连接者，事件 dict 完整透传。"""
    a_sent, b_sent = asyncio.run(_case_broadcast_reaches_connected())
    event = {"type": "node_added", "session_id": "s1", "node": {"node_id": "n1"}}
    assert a_sent == [event]
    assert b_sent == [event]


async def _case_disconnect_stops_delivery() -> list[Any]:
    hub = StreamHub()
    ws = _FakeSender()
    await hub.connect(ws)
    hub.disconnect(ws)
    await hub.broadcast({"type": "session_status", "session_id": "s1", "status": "running"})
    return ws.sent


def test_disconnect_stops_delivery() -> None:
    assert asyncio.run(_case_disconnect_stops_delivery()) == []


async def _case_dead_connection_removed() -> list[Any]:
    hub = StreamHub()
    dead = _FakeSender(fail_send=True)
    alive = _FakeSender()
    await hub.connect(dead)
    await hub.connect(alive)
    first = {"type": "loop_alert", "session_id": "s1"}
    await hub.broadcast(first)  # 死连接 send 抛异常，broadcast 不应炸
    second = {"type": "session_status", "session_id": "s1", "status": "ended"}
    await hub.broadcast(second)  # 死连接已剔除，只有活连接收到
    return alive.sent


def test_dead_connection_removed_and_no_raise() -> None:
    alive_sent = asyncio.run(_case_dead_connection_removed())
    assert alive_sent == [
        {"type": "loop_alert", "session_id": "s1"},
        {"type": "session_status", "session_id": "s1", "status": "ended"},
    ]


async def _case_event_passed_to_multiple() -> list[list[Any]]:
    hub = StreamHub()
    senders = [_FakeSender() for _ in range(3)]
    for ws in senders:
        await hub.connect(ws)
    event = {"type": "decision_pending", "decision": {"decision_id": "d1"}}
    await hub.broadcast(event)
    return [ws.sent for ws in senders]


def test_event_passed_to_multiple_connections() -> None:
    all_sent = asyncio.run(_case_event_passed_to_multiple())
    event = {"type": "decision_pending", "decision": {"decision_id": "d1"}}
    assert all_sent == [[event], [event], [event]]
