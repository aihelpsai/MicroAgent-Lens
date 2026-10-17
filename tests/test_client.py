"""lens.sdk.client 测试：MockTransport 端点解析 + 降级 + 序列化兜底。"""

import json
from typing import Any

import httpx

from lens.sdk.client import ExecutionResponse, LensClient


def _client(handler: Any) -> LensClient:
    return LensClient(transport=httpx.MockTransport(handler))


def test_create_session_returns_session_id() -> None:
    """create_session 发 metadata 并解析响应中的 session_id。"""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/sessions"
        assert json.loads(request.content) == {"metadata": {"user": "alice"}}
        return httpx.Response(200, json={"session_id": "s1", "status": "running"})

    client = _client(handler)
    assert client.create_session({"user": "alice"}) == "s1"


def test_create_session_without_metadata_sends_null() -> None:
    """metadata 为 None 时也发该 key（后端 SessionCreate.metadata 默认 None 接受）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == {"metadata": None}
        return httpx.Response(200, json={"session_id": "s2", "status": "running"})

    client = _client(handler)
    assert client.create_session() == "s2"


def test_execution_request_parses_reject_loop() -> None:
    """reject:loop 解析出 decision/reason/decision_id 三字段。"""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/execution-request"
        assert json.loads(request.content) == {
            "session_id": "s1",
            "tool_name": "search",
            "args": {"q": "x"},
        }
        return httpx.Response(
            200, json={"decision": "reject", "reason": "loop", "decision_id": "d1"}
        )

    client = _client(handler)
    resp = client.execution_request("s1", "search", {"q": "x"})
    assert resp == ExecutionResponse("reject", "loop", "d1")


def test_execution_request_parses_allow_null_reason() -> None:
    """allow 时 reason 为 null。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"decision": "allow", "reason": None, "decision_id": "d2"})

    client = _client(handler)
    resp = client.execution_request("s1", "search", {})
    assert resp == ExecutionResponse("allow", None, "d2")
    assert resp.reason is None


def test_silent_endpoints_no_raise() -> None:
    """tool_result / thought / end_session 正常路径不抛，且路径正确。"""

    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(f"{request.method} {request.url.path}")
        return httpx.Response(200, json={})

    client = _client(handler)
    client.tool_result("s1", "search", True, result="ok")
    client.thought("s1", "thinking")
    client.end_session("s1")
    assert paths == [
        "POST /v1/tool-result",
        "POST /v1/thought",
        "POST /v1/sessions/s1/end",
    ]


def test_breakpoints_roundtrip() -> None:
    """get_breakpoints / put_breakpoints 正常往返。"""

    config = {
        "suspend_tools": ["search"],
        "loop_breaker": {"window_size": 3, "similarity_threshold": 0.9},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/breakpoints"
        if request.method == "GET":
            return httpx.Response(200, json=config)
        assert json.loads(request.content) == config
        return httpx.Response(200, json=config)

    client = _client(handler)
    assert client.get_breakpoints() == config
    assert (
        client.put_breakpoints(["search"], {"window_size": 3, "similarity_threshold": 0.9})
        == config
    )


def test_degradation_connect_error() -> None:
    """后端不可达：execution_request 放行、create_session 返回 None、其余静默不抛。"""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = _client(handler)
    assert client.execution_request("s1", "search", {}) == ExecutionResponse("allow", None, "")
    assert client.create_session() is None
    assert client.get_breakpoints() is None
    assert client.put_breakpoints(["search"]) is None
    client.tool_result("s1", "search", True)
    client.thought("s1", "hi")
    client.end_session("s1")


def test_not_found_degrades() -> None:
    """404 响应经 raise_for_status 抛 HTTPStatusError，走同一降级路径。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "x"})

    client = _client(handler)
    assert client.execution_request("s1", "search", {}) == ExecutionResponse("allow", None, "")
    assert client.create_session() is None
    assert client.get_breakpoints() is None
    assert client.put_breakpoints(["search"]) is None
    client.tool_result("s1", "search", True)
    client.thought("s1", "hi")
    client.end_session("s1")


def test_tool_result_serialization_fallback() -> None:
    """不可 JSON 序列化的 result 按 _json_safe 兜底为 repr 字符串，不抛。"""

    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={})

    client = _client(handler)
    bad = object()
    client.tool_result("s1", "search", True, result={"x": bad})
    assert len(bodies) == 1
    assert bodies[0]["result"] == repr({"x": bad})
