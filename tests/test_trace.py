"""lens.sdk.trace 测试：session 生命周期 + suspend 声明合并 + log_thought 降级。"""

from typing import Any

import httpx
import pytest

from lens.sdk import trace
from lens.sdk.client import LensClient


class StubClient:
    """手写 stub：记录调用，供 start_session / end_session 注入。"""

    def __init__(
        self,
        session_id: str | None = "s1",
        breakpoints: dict[str, Any] | None = None,
    ) -> None:
        self.session_id = session_id
        self.breakpoints = breakpoints
        self.create_calls: list[dict[str, Any] | None] = []
        self.put_calls: list[tuple[list[str], dict[str, Any] | None]] = []
        self.end_calls: list[str] = []
        self.thought_calls: list[tuple[str, str]] = []

    def create_session(self, metadata: dict[str, Any] | None = None) -> str | None:
        self.create_calls.append(metadata)
        return self.session_id

    def get_breakpoints(self) -> dict[str, Any] | None:
        return self.breakpoints

    def put_breakpoints(
        self, suspend_tools: list[str], loop_breaker: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        self.put_calls.append((suspend_tools, loop_breaker))
        return None

    def end_session(self, session_id: str) -> None:
        self.end_calls.append(session_id)

    def thought(self, session_id: str, content: str) -> None:
        self.thought_calls.append((session_id, content))


@pytest.fixture(autouse=True)
def _clean_trace_state() -> Any:
    """清理模块级状态，避免测试间串扰。"""
    trace._suspend_tools.clear()
    trace._current_session.set(None)
    yield
    trace._suspend_tools.clear()
    trace._current_session.set(None)


def test_start_session_merges_and_sets_contextvar() -> None:
    """start_session 正常：create_session 被调 + 并集 PUT + contextvar 写入。"""
    trace.register_suspend_tool("send_email")
    client = StubClient(
        breakpoints={
            "suspend_tools": ["other"],
            "loop_breaker": {"window_size": 3, "similarity_threshold": 0.9},
        }
    )

    sid = trace.start_session({"user": "alice"}, client=client)

    assert sid == "s1"
    assert client.create_calls == [{"user": "alice"}]
    assert trace.current_session_id() == "s1"
    assert len(client.put_calls) == 1
    suspend_tools, loop_breaker = client.put_calls[0]
    assert set(suspend_tools) == {"other", "send_email"}
    assert loop_breaker == {"window_size": 3, "similarity_threshold": 0.9}


def test_start_session_degraded_returns_none() -> None:
    """create_session 返回 None（降级）：start_session 返回 None、不写 contextvar、不 PUT。"""
    client = StubClient(session_id=None)

    assert trace.start_session(client=client) is None
    assert client.create_calls == [None]
    assert client.put_calls == []
    assert trace.current_session_id() is None


def test_suspend_merge_union() -> None:
    """已有名单 ∪ 声明名单：重复项去重，loop_breaker 原样回传。"""
    trace.register_suspend_tool("send_email")
    trace.register_suspend_tool("run_code")
    client = StubClient(
        breakpoints={
            "suspend_tools": ["other", "send_email"],
            "loop_breaker": {"window_size": 5, "similarity_threshold": 0.8},
        }
    )

    trace.start_session(client=client)

    suspend_tools, loop_breaker = client.put_calls[0]
    assert set(suspend_tools) == {"other", "send_email", "run_code"}
    assert loop_breaker == {"window_size": 5, "similarity_threshold": 0.8}


def test_log_thought_silent_without_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """无 session：log_thought 直接 return，client.thought 不被调。"""
    client = StubClient()
    monkeypatch.setattr(trace, "get_default_client", lambda: client)

    trace.log_thought("thinking...")

    assert client.thought_calls == []


def test_log_thought_with_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """有 session：log_thought 调 client.thought。"""
    client = StubClient(breakpoints={"suspend_tools": [], "loop_breaker": None})
    monkeypatch.setattr(trace, "get_default_client", lambda: client)
    trace.start_session(client=client)

    trace.log_thought("thinking...")

    assert client.thought_calls == [("s1", "thinking...")]


def test_end_session_clears_and_posts() -> None:
    """end_session：清 contextvar 且 client.end_session 被调。"""
    client = StubClient(breakpoints={"suspend_tools": [], "loop_breaker": None})
    trace.start_session(client=client)

    trace.end_session(client=client)

    assert trace.current_session_id() is None
    assert client.end_calls == ["s1"]


def test_end_session_clears_even_if_backend_unreachable() -> None:
    """后端不可达：client.end_session 内部静默，contextvar 仍必清。"""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = LensClient(transport=httpx.MockTransport(handler))
    trace._current_session.set("s1")

    trace.end_session(client=client)

    assert trace.current_session_id() is None


def test_end_session_silent_without_session() -> None:
    """无 session：end_session 不调 client.end_session，也不抛。"""
    client = StubClient()

    trace.end_session(client=client)

    assert client.end_calls == []
    assert trace.current_session_id() is None
