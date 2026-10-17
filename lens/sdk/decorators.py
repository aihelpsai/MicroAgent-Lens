"""lens.sdk.decorators：bind_tool 装饰器（三语义分派）。

三语义分派是协议响应分派（按后端返回的 decision / reason 分派），非决策逻辑：
allow → 执行 + 记录 tool_result；reject:loop → 抛 AgentLoopException；
reject:human → 抛 ToolRejected。熔断 / 断点判定仍在后端（不变量 2）。
"""

import functools
import inspect
from collections.abc import Callable
from typing import Any

from lens.sdk.client import get_default_client
from lens.sdk.errors import AgentLoopException, ToolRejected
from lens.sdk.trace import current_session_id, register_suspend_tool


def bind_tool(suspend: bool = False) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """工具装饰器：suspend=True 时声明该工具参与断点挂起。"""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if suspend:
            register_suspend_tool(func.__name__)  # 收集在 trace.py（D7）

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            sid = current_session_id()
            if sid is None:
                return func(*args, **kwargs)  # 未 start_session：降级直接执行
            bound = inspect.signature(func).bind(*args, **kwargs)
            client = get_default_client()
            resp = client.execution_request(sid, func.__name__, dict(bound.arguments))
            if resp.decision == "allow":
                try:
                    result = func(*args, **kwargs)
                except Exception as e:
                    # 内部吞，不抛：记录失败 Observation，原异常继续重抛
                    client.tool_result(sid, func.__name__, ok=False, error=str(e))
                    raise
                # 内部吞，不抛：成功分支在 try 外，避免序列化失败被工具异常 except 误吞
                client.tool_result(sid, func.__name__, ok=True, result=result)
                return result
            if resp.reason == "loop":
                raise AgentLoopException(resp.decision_id, func.__name__, dict(bound.arguments))
            raise ToolRejected(resp.decision_id, func.__name__, dict(bound.arguments))

        return wrapper

    return decorator
