"""WS 五类事件验收：session_status / node_added / loop_alert / decision_pending / decision_resolved。

用 TestClient.websocket_connect 连 /v1/stream，前三个非阻塞事件单线程即可；
decision_pending / decision_resolved 为阻塞事件，用后台线程发挂起请求 + 主线程收事件。
"""

import threading
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from lens.server.app import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """每个用例独立临时库的 TestClient。"""
    with TestClient(create_app(tmp_path / "ws.db")) as c:
        yield c


def _create_session(client: TestClient) -> str:
    resp = client.post("/v1/sessions", json={})
    assert resp.status_code == 200
    return resp.json()["session_id"]


def test_ws_session_status(client: TestClient) -> None:
    """建会话后收到 session_status(running)。"""
    with client.websocket_connect("/v1/stream") as ws:
        client.post("/v1/sessions", json={})
        evt = ws.receive_json()
        assert evt["type"] == "session_status"
        assert evt["status"] == "running"


def test_ws_node_added(client: TestClient) -> None:
    """建会话后记 thought，按序收到 session_status 再 node_added(thought)。"""
    with client.websocket_connect("/v1/stream") as ws:
        sid = _create_session(client)
        client.post("/v1/thought", json={"session_id": sid, "content": "hi"})
        first = ws.receive_json()
        assert first["type"] == "session_status"
        second = ws.receive_json()
        assert second["type"] == "node_added"
        assert second["node"]["type"] == "thought"
        assert second["session_id"] == sid


def test_ws_loop_alert(client: TestClient) -> None:
    """同名同参连发 3 次，跳过中间 node_added 直到出现 loop_alert。"""
    with client.websocket_connect("/v1/stream") as ws:
        sid = _create_session(client)
        payload = {"session_id": sid, "tool_name": "search", "args": {"q": "x"}}
        client.post("/v1/execution-request", json=payload)
        client.post("/v1/execution-request", json=payload)
        client.post("/v1/execution-request", json=payload)
        evt = None
        for _ in range(50):
            evt = ws.receive_json()
            if evt["type"] == "loop_alert":
                break
        assert evt is not None and evt["type"] == "loop_alert"
        assert evt["session_id"] == sid
        assert evt["tool_name"] == "search"
        assert evt["decision_id"]


def test_ws_decision_pending_and_resolved(client: TestClient) -> None:
    """后台线程发挂起请求，主线程收 decision_pending → resolve → 收 decision_resolved。"""
    with client.websocket_connect("/v1/stream") as ws:
        sid = _create_session(client)
        client.put("/v1/breakpoints", json={"suspend_tools": ["send_email"]})
        assert ws.receive_json()["type"] == "session_status"

        result: dict[str, httpx.Response] = {}

        def fire() -> None:
            result["resp"] = client.post(
                "/v1/execution-request",
                json={"session_id": sid, "tool_name": "send_email", "args": {}},
            )

        thread = threading.Thread(target=fire)
        thread.start()
        evt = None
        for _ in range(100):
            evt = ws.receive_json()
            if evt["type"] == "decision_pending":
                break
        assert evt is not None and evt["type"] == "decision_pending"
        did = evt["decision"]["decision_id"]
        client.post(f"/v1/decisions/{did}/resolve", json={"action": "allow"})
        evt2 = None
        for _ in range(100):
            evt2 = ws.receive_json()
            if evt2["type"] == "decision_resolved":
                break
        assert evt2 is not None and evt2["type"] == "decision_resolved"
        thread.join()
        assert result["resp"].json()["decision"] == "allow"
