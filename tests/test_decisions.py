"""挂起决策注册表 DecisionRegistry 测试。"""

import asyncio

from lens.server.decisions import DecisionRegistry


async def _register_then_resolve_allow() -> str:
    registry = DecisionRegistry()
    future = registry.register("d1")
    assert not future.done()
    assert registry.is_pending("d1") is True
    assert registry.resolve("d1", "allow") is True
    assert registry.is_pending("d1") is False
    return await future


def test_register_returns_pending_then_resolve_allow() -> None:
    """register 返回未完成 Future；resolve(allow) 后 await 得 allow；is_pending 翻转。"""
    assert asyncio.run(_register_then_resolve_allow()) == "allow"


async def _resolve_reject() -> str:
    registry = DecisionRegistry()
    future = registry.register("d1")
    registry.resolve("d1", "reject")
    return await future


def test_resolve_reject() -> None:
    assert asyncio.run(_resolve_reject()) == "reject"


async def _resolve_missing() -> bool:
    registry = DecisionRegistry()
    return registry.resolve("missing", "allow")


def test_resolve_missing_returns_false() -> None:
    assert asyncio.run(_resolve_missing()) is False


async def _double_resolve() -> tuple[bool, bool]:
    registry = DecisionRegistry()
    registry.register("d1")
    first = registry.resolve("d1", "allow")
    second = registry.resolve("d1", "allow")
    return first, second


def test_double_resolve_second_returns_false() -> None:
    assert asyncio.run(_double_resolve()) == (True, False)


async def _is_pending_flips() -> tuple[bool, bool]:
    registry = DecisionRegistry()
    registry.register("d1")
    before = registry.is_pending("d1")
    registry.resolve("d1", "allow")
    after = registry.is_pending("d1")
    return before, after


def test_is_pending_flips_around_resolve() -> None:
    assert asyncio.run(_is_pending_flips()) == (True, False)
