"""Loop Breaker 熔断判定：滑动窗口内连续同名同参调用即触发熔断。

所有函数为纯函数：无全局可变状态、无 I/O，仅依赖入参与内置库。
"""

import difflib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

DEFAULT_WINDOW_SIZE = 3
DEFAULT_SIMILARITY_THRESHOLD = 0.9


@dataclass(frozen=True)
class ToolCall:
    """一次工具调用的快照：工具名与参数。"""

    tool_name: str
    args: dict[str, Any]


def serialize_args(args: dict[str, Any]) -> str:
    """将参数字典序列化为稳定字符串（键排序，规避插入顺序差异）。"""
    return json.dumps(args, sort_keys=True)


def args_similarity(a: str, b: str) -> float:
    """计算两段序列化参数的相似度（0.0 ~ 1.0）。"""
    return difflib.SequenceMatcher(None, a, b).ratio()


def is_same_call(
    a: ToolCall,
    b: ToolCall,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> bool:
    """同名且参数相似度达阈值即视为同一次调用。"""
    return (
        a.tool_name == b.tool_name
        and args_similarity(serialize_args(a.args), serialize_args(b.args)) >= threshold
    )


def should_break(
    recent_calls: Sequence[ToolCall],
    current: ToolCall,
    window_size: int = DEFAULT_WINDOW_SIZE,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> bool:
    """判定当前调用是否应触发熔断。

    语义：recent_calls 为滑窗内最近历史（不含当前），当前调用凑满 window_size 次
    连续「同名同参」即熔断。
    """
    if window_size < 2:
        # 窗口过小无法判定「重复」。
        return False
    if len(recent_calls) < window_size - 1:
        # 历史不足，尚未凑满窗口。
        return False
    tail = recent_calls[-(window_size - 1) :]
    return all(is_same_call(current, prev, threshold) for prev in tail)
