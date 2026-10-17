"""MicroAgent-Lens：纯 Python、零配置、本地自托管的 Agent 运行时调试器。"""

__version__ = "0.1.0"

from lens.sdk.decorators import bind_tool
from lens.sdk.errors import AgentLoopException, ToolRejected
from lens.sdk.trace import end_session, log_thought, start_session

__all__ = [
    "start_session",
    "end_session",
    "bind_tool",
    "log_thought",
    "AgentLoopException",
    "ToolRejected",
]
