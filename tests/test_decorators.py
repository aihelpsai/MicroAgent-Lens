"""lens.sdk.decorators 测试：bind_tool 三语义分派 + 降级 + 工具异常传播。"""

from typing import Any

import pytest

from lens.sdk import decorators, trace
from lens.sdk.client import ExecutionResponse
from lens.sdk.errors import AgentLoopException, ToolRejected


class StubClient:
    """手写 stub：记录 execution_request / tool_result 调用，返回固定决策。"""

    def __init__(self, response: ExecutionResponse) -> None:
        self.response = response
        self.execution_calls: list[tuple[str, str, dict[str, Any]]] = []
        self.tool_result_calls: list[tuple[str, str, bool, Any, str | None, int | None]] = []

    def execution_request(
        self, session_id: str, tool_name: str, args: dict[str, Any]
    ) -> ExecutionResponse:
        self.execution_calls.append((session_id, tool_name, args))
        return self.response

    def tool_result(
        self,
        session_id: str,
        tool_name: str,
        ok: bool,
        result: Any = None,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        self.tool_result_calls.append((session_id, tool_name, ok, result, error, duration_ms))


@pytest.fixture(autouse=True)
def _clean_decorator_state() -> Any:
    """清理模块级状态，避免测试间串扰。"""
    trace._suspend_tools.clear()
    trace._current_session.set(None)
    yield
    trace._suspend_tools.clear()
    trace._current_session.set(None)


def test_allow_executes_and_records(monkeypatch: pytest.MonkeyPatch) -> None:
    """allow：工具执行 + tool_result(ok=True) 记录 + 返回工具结果。"""
    client = StubClient(ExecutionResponse("allow", None, "d1"))
    monkeypatch.setattr(decorators, "get_default_client", lambda: client)
    trace._current_session.set("s1")

    @decorators.bind_tool()
    def add(a: int, b: int) -> int:
        return a + b

    assert add(1, 2) == 3
    assert client.execution_calls == [("s1", "add", {"a": 1, "b": 2})]
    assert len(client.tool_result_calls) == 1
    session_id, tool_name, ok, result, error, duration_ms = client.tool_result_calls[0]
    assert (session_id, tool_name, ok) == ("s1", "add", True)
    assert result == 3
    assert error is None


def test_reject_loop_raises_agent_loop_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """reject:loop：抛 AgentLoopException，工具不执行。"""
    client = StubClient(ExecutionResponse("reject", "loop", "d2"))
    monkeypatch.setattr(decorators, "get_default_client", lambda: client)
    trace._current_session.set("s1")
    executed: list[Any] = []

    @decorators.bind_tool()
    def search(q: str) -> str:
        executed.append(q)
        return q

    with pytest.raises(AgentLoopException):
        search("x")

    assert executed == []


def test_reject_human_raises_tool_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """reject:human：抛 ToolRejected，工具不执行。"""
    client = StubClient(ExecutionResponse("reject", "human", "d3"))
    monkeypatch.setattr(decorators, "get_default_client", lambda: client)
    trace._current_session.set("s1")
    executed: list[Any] = []

    @decorators.bind_tool()
    def write_file(path: str) -> str:
        executed.append(path)
        return path

    with pytest.raises(ToolRejected):
        write_file("/tmp/a")

    assert executed == []


def test_no_session_executes_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    """未 start_session：工具直接执行，不碰任何 HTTP。"""
    client = StubClient(ExecutionResponse("allow", None, "d1"))
    monkeypatch.setattr(decorators, "get_default_client", lambda: client)
    # fixture 已清 contextvar，此处显式置 None
    trace._current_session.set(None)

    @decorators.bind_tool()
    def add(a: int, b: int) -> int:
        return a + b

    assert add(2, 3) == 5
    assert client.execution_calls == []
    assert client.tool_result_calls == []


def test_tool_exception_records_and_reraises(monkeypatch: pytest.MonkeyPatch) -> None:
    """allow 后工具抛异常：tool_result(ok=False, error=...) 记录 + 原异常重抛。"""
    client = StubClient(ExecutionResponse("allow", None, "d1"))
    monkeypatch.setattr(decorators, "get_default_client", lambda: client)
    trace._current_session.set("s1")

    @decorators.bind_tool()
    def boom() -> None:
        raise ValueError("bad")

    with pytest.raises(ValueError):
        boom()

    assert len(client.tool_result_calls) == 1
    session_id, tool_name, ok, result, error, duration_ms = client.tool_result_calls[0]
    assert (session_id, tool_name, ok) == ("s1", "boom", False)
    assert error == "bad"


def test_suspend_true_registers_tool_name() -> None:
    """bind_tool(suspend=True) 装饰时登记工具名到 trace。"""
    trace._suspend_tools.clear()

    @decorators.bind_tool(suspend=True)
    def send_email(to: str) -> str:
        return to

    assert "send_email" in trace._suspend_tools
