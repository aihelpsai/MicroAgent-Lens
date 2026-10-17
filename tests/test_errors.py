"""lens.sdk.errors 异常类型测试。"""

import pytest

from lens.sdk.errors import AgentLoopException, ToolRejected


def test_agent_loop_exception_attributes() -> None:
    """构造保留 decision_id / tool_name / args，且是 Exception 子类、str 为中文消息。"""
    exc = AgentLoopException("d1", "search", {"q": "x"})
    assert exc.decision_id == "d1"
    assert exc.tool_name == "search"
    assert exc.args == {"q": "x"}
    assert isinstance(exc, Exception)
    assert str(exc) == "死循环熔断：工具 search 连续重复调用被终止"


def test_tool_rejected_attributes() -> None:
    """构造保留 decision_id / tool_name / args，且是 Exception 子类、str 为中文消息。"""
    exc = ToolRejected("d2", "write_file", {"path": "/tmp/a"})
    assert exc.decision_id == "d2"
    assert exc.tool_name == "write_file"
    assert exc.args == {"path": "/tmp/a"}
    assert isinstance(exc, Exception)
    assert str(exc) == "工具 write_file 被人工拒绝"


def test_exceptions_are_not_subclasses_of_each_other() -> None:
    """两异常不同源：互不为子类，agent 可精确 except 区分。"""
    assert not issubclass(ToolRejected, AgentLoopException)
    assert not issubclass(AgentLoopException, ToolRejected)


def test_catch_precision() -> None:
    """捕获 AgentLoopException 不会吞掉 ToolRejected，反之亦然。"""
    with pytest.raises(ToolRejected):
        raise ToolRejected("d", "t", {})
    with pytest.raises(AgentLoopException):
        raise AgentLoopException("d", "t", {})
