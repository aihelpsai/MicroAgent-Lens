"""阶段 3 HTTP API 冒烟：8 端点（10 操作）字段对齐 openapi + 404 分支。"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lens.server.app import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """每个用例独立临时库的 TestClient。"""
    with TestClient(create_app(tmp_path / "test.db")) as c:
        yield c


def _create_session(client: TestClient) -> str:
    resp = client.post("/v1/sessions", json={})
    assert resp.status_code == 200
    return resp.json()["session_id"]


# ---- POST /v1/sessions ----


def test_create_session_fields(client: TestClient) -> None:
    resp = client.post("/v1/sessions", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"]
    assert body["status"] == "running"
    assert body["created_at"]
    assert body["ended_at"] is None


def test_create_session_metadata_roundtrip(client: TestClient) -> None:
    resp = client.post("/v1/sessions", json={"metadata": {"agent": "demo", "n": 1}})
    assert resp.status_code == 200
    assert resp.json()["metadata"] == {"agent": "demo", "n": 1}


# ---- GET /v1/sessions ----


def test_list_sessions_fields(client: TestClient) -> None:
    _create_session(client)
    resp = client.get("/v1/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["sessions"], list)
    assert len(body["sessions"]) == 1
    item = body["sessions"][0]
    assert item["session_id"]
    assert item["status"] == "running"
    assert item["created_at"]
    assert item["tool_count"] == 0
    assert item["token_usage"] == 0


# ---- GET /v1/sessions/{sid} ----


def test_get_session_detail_three_keys(client: TestClient) -> None:
    sid = _create_session(client)
    resp = client.get(f"/v1/sessions/{sid}")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"session", "trace", "pending_decisions"}
    assert body["session"]["session_id"] == sid
    assert body["trace"] == []
    assert body["pending_decisions"] == []


def test_get_session_missing_404(client: TestClient) -> None:
    resp = client.get("/v1/sessions/missing")
    assert resp.status_code == 404
    assert resp.json()["error"]


# ---- POST /v1/sessions/{sid}/end ----


def test_end_session_fields(client: TestClient) -> None:
    sid = _create_session(client)
    resp = client.post(f"/v1/sessions/{sid}/end")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ended"
    assert body["ended_at"]


def test_end_session_missing_404(client: TestClient) -> None:
    resp = client.post("/v1/sessions/missing/end")
    assert resp.status_code == 404
    assert resp.json()["error"]


# ---- POST /v1/execution-request ----


def test_execution_request_allow_branch(client: TestClient) -> None:
    sid = _create_session(client)
    resp = client.post(
        "/v1/execution-request",
        json={"session_id": sid, "tool_name": "search", "args": {"q": "x"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] == "allow"
    assert body["reason"] is None
    assert body["decision_id"]


def test_execution_request_missing_404(client: TestClient) -> None:
    resp = client.post(
        "/v1/execution-request",
        json={"session_id": "missing", "tool_name": "search", "args": {}},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]


# ---- POST /v1/tool-result ----


def test_tool_result_ok(client: TestClient) -> None:
    sid = _create_session(client)
    resp = client.post(
        "/v1/tool-result",
        json={"session_id": sid, "tool_name": "search", "ok": True, "result": {"n": 1}},
    )
    assert resp.status_code == 200
    assert resp.json() == {}


def test_tool_result_missing_404(client: TestClient) -> None:
    resp = client.post(
        "/v1/tool-result",
        json={"session_id": "missing", "tool_name": "search", "ok": True},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]


# ---- POST /v1/thought ----


def test_thought_ok(client: TestClient) -> None:
    sid = _create_session(client)
    resp = client.post("/v1/thought", json={"session_id": sid, "content": "thinking..."})
    assert resp.status_code == 200
    assert resp.json() == {}


def test_thought_missing_404(client: TestClient) -> None:
    resp = client.post("/v1/thought", json={"session_id": "missing", "content": "x"})
    assert resp.status_code == 404
    assert resp.json()["error"]


# ---- GET /v1/breakpoints ----


def test_get_breakpoints_defaults(client: TestClient) -> None:
    resp = client.get("/v1/breakpoints")
    assert resp.status_code == 200
    body = resp.json()
    assert body["suspend_tools"] == []
    assert body["loop_breaker"] == {"window_size": 3, "similarity_threshold": 0.9}


# ---- PUT /v1/breakpoints ----


def test_put_breakpoints_updated(client: TestClient) -> None:
    resp = client.put(
        "/v1/breakpoints",
        json={
            "suspend_tools": ["search"],
            "loop_breaker": {"window_size": 5, "similarity_threshold": 0.8},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["suspend_tools"] == ["search"]
    assert body["loop_breaker"] == {"window_size": 5, "similarity_threshold": 0.8}


# ---- POST /v1/decisions/{did}/resolve ----


def test_resolve_missing_decision_404(client: TestClient) -> None:
    resp = client.post("/v1/decisions/missing/resolve", json={"action": "allow"})
    assert resp.status_code == 404
    assert resp.json()["error"]
