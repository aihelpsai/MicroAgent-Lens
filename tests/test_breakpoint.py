"""Active Breakpoint suspend 名单命中判定测试。"""

from lens.server.breakpoint import is_suspended


def test_tool_in_list_suspends() -> None:
    assert is_suspended("search", ["search", "calc"]) is True


def test_tool_not_in_list_does_not_suspend() -> None:
    assert is_suspended("browse", ["search", "calc"]) is False


def test_empty_list_does_not_suspend() -> None:
    assert is_suspended("search", []) is False
