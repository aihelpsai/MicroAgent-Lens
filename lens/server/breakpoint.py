"""Active Breakpoint suspend 名单命中判定：纯函数。"""

from collections.abc import Collection


def is_suspended(tool_name: str, suspend_tools: Collection[str]) -> bool:
    """工具名命中 suspend 名单即暂停，等待人机协同决策。"""
    return tool_name in suspend_tools
