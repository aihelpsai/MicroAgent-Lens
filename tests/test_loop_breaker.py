"""Loop Breaker 熔断判定纯函数测试。"""

from lens.server.loop_breaker import (
    DEFAULT_SIMILARITY_THRESHOLD,
    ToolCall,
    args_similarity,
    is_same_call,
    serialize_args,
    should_break,
)


def _call(name: str, x: int) -> ToolCall:
    """构造带单键参数的 ToolCall，便于书写测试。"""
    return ToolCall(tool_name=name, args={"x": x})


def test_serialize_args_is_key_order_stable() -> None:
    """不同键插入顺序应得到相同序列化结果。"""
    assert serialize_args({"b": 1, "a": 2}) == serialize_args({"a": 2, "b": 1})


def test_three_identical_calls_trigger_break() -> None:
    """窗口 3 内连续同名同参触发熔断。"""
    recent = [_call("tool", 1), _call("tool", 1)]
    current = _call("tool", 1)
    assert should_break(recent, current) is True


def test_different_args_do_not_trigger() -> None:
    recent = [_call("tool", 1), _call("tool", 1)]
    current = _call("tool", 2)
    assert should_break(recent, current) is False


def test_different_name_does_not_trigger() -> None:
    recent = [_call("toolA", 1), _call("toolA", 1)]
    current = _call("toolB", 1)
    assert should_break(recent, current) is False


def test_window_slides_out_stale_matches() -> None:
    """历史超出窗口后只看末尾 window-1 个，前 3 个匹配被滑出不应误判。"""
    recent = [
        _call("tool", 1),
        _call("tool", 1),
        _call("tool", 1),
        _call("tool", 9),
        _call("tool", 9),
    ]
    current = _call("tool", 1)
    assert should_break(recent, current) is False


def test_insufficient_history_does_not_trigger() -> None:
    """历史不足 window-1 时不触发。"""
    recent = [_call("tool", 1)]
    current = _call("tool", 1)
    assert should_break(recent, current) is False


def test_similarity_boundary_is_inclusive() -> None:
    """{"a": "x"} 与 {"a": "y"} 序列化后各 10 字符、仅 1 字符不同，
    SequenceMatcher ratio = 2*9/20 = 0.9，恰为默认阈值，>= 语义应判定为同调用。"""
    s1 = serialize_args({"a": "x"})
    s2 = serialize_args({"a": "y"})
    ratio = args_similarity(s1, s2)
    assert ratio >= DEFAULT_SIMILARITY_THRESHOLD
    assert is_same_call(ToolCall("tool", {"a": "x"}), ToolCall("tool", {"a": "y"})) is True
