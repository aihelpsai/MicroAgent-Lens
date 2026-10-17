"""lens.sdk 异常类型：三语义分派中的两种异常结果。

reject:loop 抛 AgentLoopException（终止 agent），reject:human 抛 ToolRejected（非致命，
agent 捕获后走错误分支）。两异常不同源（无共同基类），保证 agent 能精确 except 区分
「终止 vs 非致命」。
"""

from typing import Any


class AgentLoopException(Exception):  # noqa: N818  # 公共 API 名称由设计定死
    """死循环熔断：reject:loop。终止 agent，顶层捕获后停止。"""

    _tool_args: dict[str, Any]

    def __init__(self, decision_id: str, tool_name: str, args: dict[str, Any]) -> None:
        super().__init__(f"死循环熔断：工具 {tool_name} 连续重复调用被终止")
        self.decision_id = decision_id
        self.tool_name = tool_name
        self.args = args

    @property  # type: ignore[override]  # BaseException.args 是 getset 描述符（强制 tuple），此处覆盖为参数字典
    def args(self) -> dict[str, Any]:
        """工具调用参数字典，供 agent 记录。"""
        return self._tool_args

    @args.setter
    def args(self, value: dict[str, Any]) -> None:
        self._tool_args = value


class ToolRejected(Exception):  # noqa: N818  # 公共 API 名称由设计定死
    """断点被拒绝：reject:human。专用非致命异常，agent 捕获走错误分支。"""

    _tool_args: dict[str, Any]

    def __init__(self, decision_id: str, tool_name: str, args: dict[str, Any]) -> None:
        super().__init__(f"工具 {tool_name} 被人工拒绝")
        self.decision_id = decision_id
        self.tool_name = tool_name
        self.args = args

    @property  # type: ignore[override]  # BaseException.args 是 getset 描述符（强制 tuple），此处覆盖为参数字典
    def args(self) -> dict[str, Any]:
        """工具调用参数字典，供 agent 记录。"""
        return self._tool_args

    @args.setter
    def args(self, value: dict[str, Any]) -> None:
        self._tool_args = value
