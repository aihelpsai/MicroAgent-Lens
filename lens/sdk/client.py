"""lens.sdk.client：薄协议 client（同步 httpx）。

所有智能（熔断 / 断点 / 相似度）都在 server；本模块只「发 HTTP + 阻塞等响应 + 解析」。
降级保证（不变量 1）：后端不可达或出错时 execution_request 放行、create_session 返回 None、
其余端点静默返回 None，绝不抛给 agent。
"""

import json
import os
from dataclasses import dataclass
from typing import Any, Literal, cast

import httpx

DEFAULT_BASE_URL = "http://localhost:7878"


def _json_safe(value: Any) -> Any:
    """序列化预检（D10）：json.dumps 成功则原样返回，否则 repr 兜底。"""
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)


@dataclass(frozen=True)
class ExecutionResponse:
    """execution_request 的决策结果。"""

    decision: Literal["allow", "reject"]
    reason: Literal["loop", "human"] | None
    decision_id: str


class LensClient:
    """薄协议 client：5 个 POST + breakpoints GET/PUT，同步 httpx。"""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def create_session(self, metadata: dict[str, Any] | None = None) -> str | None:
        """创建会话；后端不可达降级返回 None。"""
        try:
            resp = self._client.post("/v1/sessions", json={"metadata": metadata})
            resp.raise_for_status()
        except httpx.HTTPError:
            return None
        return cast(str, resp.json().get("session_id"))

    def execution_request(
        self, session_id: str, tool_name: str, args: dict[str, Any]
    ) -> ExecutionResponse:
        """统一决策端点（timeout=None 无限等待，断点长挂）；降级返回 allow 哨兵。"""
        try:
            resp = self._client.post(
                "/v1/execution-request",
                json={"session_id": session_id, "tool_name": tool_name, "args": args},
                timeout=None,
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return ExecutionResponse("allow", None, "")
        data = resp.json()
        decision = cast(Literal["allow", "reject"], data.get("decision"))
        reason = cast(Literal["loop", "human"] | None, data.get("reason"))
        decision_id = cast(str, data.get("decision_id"))
        return ExecutionResponse(decision, reason, decision_id)

    def tool_result(
        self,
        session_id: str,
        tool_name: str,
        ok: bool,
        result: Any = None,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """记录工具结果；静默端点，吞一切异常（含 result 序列化失败）。"""
        try:
            resp = self._client.post(
                "/v1/tool-result",
                json={
                    "session_id": session_id,
                    "tool_name": tool_name,
                    "ok": ok,
                    "result": _json_safe(result),
                    "error": error,
                    "duration_ms": duration_ms,
                },
            )
            resp.raise_for_status()
        except Exception:
            return

    def thought(self, session_id: str, content: str) -> None:
        """记录 Thought；静默端点，吞一切异常。"""
        try:
            resp = self._client.post(
                "/v1/thought", json={"session_id": session_id, "content": content}
            )
            resp.raise_for_status()
        except Exception:
            return

    def end_session(self, session_id: str) -> None:
        """结束会话；静默端点，吞一切异常。"""
        try:
            resp = self._client.post(f"/v1/sessions/{session_id}/end")
            resp.raise_for_status()
        except Exception:
            return

    def get_breakpoints(self) -> dict[str, Any] | None:
        """读取断点配置；静默端点，降级返回 None。"""
        try:
            resp = self._client.get("/v1/breakpoints")
            resp.raise_for_status()
        except Exception:
            return None
        return cast(dict[str, Any], resp.json())

    def put_breakpoints(
        self, suspend_tools: list[str], loop_breaker: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """更新断点配置；静默端点，降级返回 None。

        loop_breaker 传 {"window_size": int, "similarity_threshold": float}，
        为 None 时后端回默认值。
        """
        try:
            resp = self._client.put(
                "/v1/breakpoints",
                json={"suspend_tools": suspend_tools, "loop_breaker": loop_breaker},
            )
            resp.raise_for_status()
        except Exception:
            return None
        return cast(dict[str, Any], resp.json())

    def close(self) -> None:
        """关闭底层 httpx.Client。"""
        self._client.close()


_default_client: LensClient | None = None


def get_default_client() -> LensClient:
    """惰性单例；读 LENS_BASE_URL 覆盖默认地址。"""
    global _default_client
    if _default_client is None:
        _default_client = LensClient(base_url=os.environ.get("LENS_BASE_URL", DEFAULT_BASE_URL))
    return _default_client
