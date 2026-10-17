"""lens.sdk.trace：会话 / 追踪管理（contextvars）+ suspend 声明收集。

import 方向单向：decorators → trace → client（无循环 import）。
suspend 声明的收集 / 读取放本模块（register_suspend_tool / _declared_suspend_tools），
decorators 只登记、不持有集合——若把集合放 decorators 会造成 trace ↔ decorators 循环 import。
"""

from contextvars import ContextVar
from typing import Any

from lens.sdk.client import LensClient, get_default_client

_current_session: ContextVar[str | None] = ContextVar("lens_session", default=None)
_suspend_tools: set[str] = set()  # 装饰时收集，非运行时可变


def register_suspend_tool(name: str) -> None:
    """bind_tool(suspend=True) 装饰时登记工具名。"""
    _suspend_tools.add(name)


def _declared_suspend_tools() -> frozenset[str]:
    """当前已声明的 suspend 工具名（不可变快照）。"""
    return frozenset(_suspend_tools)


def start_session(
    metadata: dict[str, Any] | None = None,
    client: LensClient | None = None,
) -> str | None:
    """create_session + 合并 suspend 名单 + 写 contextvar；后端不可达返回 None（降级）。

    流程（D7/D9）：create_session → GET breakpoints → 并集声明名单 → PUT（loop_breaker
    原样回传，避免覆盖用户已调参数）→ 写 contextvar。
    """
    c = client or get_default_client()
    sid = c.create_session(metadata)
    if sid is None:
        return None
    existing = c.get_breakpoints()
    existing_tools = set(existing["suspend_tools"]) if existing else set()
    merged = existing_tools | _declared_suspend_tools()
    loop_breaker = existing["loop_breaker"] if existing else None
    c.put_breakpoints(list(merged), loop_breaker=loop_breaker)
    _current_session.set(sid)
    return sid


def end_session(client: LensClient | None = None) -> None:
    """必清 contextvar + 尽力 POST end（失败静默）。

    清 contextvar 是必然动作（先于 POST）；POST 是尽力而为，client.end_session 内部已吞
    异常，此处再兜一层防御注入的 mock client。
    """
    sid = _current_session.get()
    _current_session.set(None)
    if sid is not None:
        c = client or get_default_client()
        try:
            c.end_session(sid)
        except Exception:  # noqa: BLE001  # 降级语义：吞一切，清 contextvar 不受影响
            return


def current_session_id() -> str | None:
    """当前 contextvar 中的 session_id；未 start_session 时为 None。"""
    return _current_session.get()


def log_thought(content: str) -> None:
    """记录 Thought；无 session 或降级时静默。"""
    sid = _current_session.get()
    if sid is None:
        return
    get_default_client().thought(sid, content)
