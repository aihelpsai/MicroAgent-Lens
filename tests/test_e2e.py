"""端到端三场景 + 真实 WS 握手：SDK（真实 httpx）↔ 真实 uvicorn server。

不用 TestClient（in-process ASGI 测不出真实 uvicorn 的 WS 层）；server 用 daemon 线程
起真实 uvicorn，SDK 经 LENS_BASE_URL 指向它。挂起场景 SDK 调用放后台线程，主线程轮询
pending_decisions 后 resolve。工具在测试函数内定义（suspend 注册先于 start_session 合并）。
"""

import json
import socket
import threading
import time
from collections.abc import Iterator
from contextvars import copy_context
from pathlib import Path

import httpx
import pytest
import uvicorn
from websockets.sync.client import connect

from lens import AgentLoopException, ToolRejected, bind_tool, end_session, start_session
from lens.sdk import client as sdk_client
from lens.sdk import trace
from lens.server.app import create_app


def _free_port() -> int:
    """绑定端口 0 取空闲端口后释放（存在极小抢占窗口，本地可接受）。"""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def server_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """起真实 uvicorn server（daemon 线程），设 LENS_BASE_URL，返回 base_url。"""
    port = _free_port()
    config = uvicorn.Config(
        create_app(tmp_path / "e2e.db"), host="127.0.0.1", port=port, log_level="error"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10.0
    while not server.started and time.time() < deadline:
        time.sleep(0.01)
    assert server.started, "uvicorn 未在 10s 内启动"
    base_url = f"http://127.0.0.1:{port}"
    monkeypatch.setenv("LENS_BASE_URL", base_url)
    yield base_url
    server.should_exit = True
    thread.join(timeout=5.0)


@pytest.fixture(autouse=True)
def _reset_sdk_state() -> Iterator[None]:
    """重置 SDK 进程级单例与 contextvar/suspend 状态，避免跨用例串扰。"""
    sdk_client._default_client = None
    trace._suspend_tools.clear()
    trace._current_session.set(None)
    yield
    sdk_client._default_client = None
    trace._suspend_tools.clear()
    trace._current_session.set(None)


def _poll_pending_decision(base_url: str, sid: str) -> str:
    """轮询会话详情的 pending_decisions 直到非空，返回 decision_id。"""
    for _ in range(200):
        detail = httpx.get(f"{base_url}/v1/sessions/{sid}").json()
        pending = detail["pending_decisions"]
        if pending:
            return str(pending[0]["decision_id"])
        time.sleep(0.01)
    raise AssertionError("挂起决策未在 2s 内出现")


def test_degrade_no_board(monkeypatch: pytest.MonkeyPatch) -> None:
    """不起看板：start_session 返回 None，工具照常执行、无异常。"""
    monkeypatch.setenv("LENS_BASE_URL", f"http://127.0.0.1:{_free_port()}")

    @bind_tool()
    def add(a: int, b: int) -> int:
        return a + b

    assert start_session() is None
    assert add(2, 3) == 5


def test_loop_breaks_on_third(server_url: str) -> None:
    """起看板：同名同参 3 次，前两次 allow、第 3 次抛 AgentLoopException。"""

    @bind_tool()
    def search(q: str) -> str:
        return q

    sid = start_session()
    assert sid is not None

    assert search("same") == "same"
    assert search("same") == "same"
    with pytest.raises(AgentLoopException):
        search("same")
    end_session()


def test_breakpoint_allow(server_url: str) -> None:
    """suspend 工具命中挂起 → resolve allow → 工具正常返回。"""

    @bind_tool(suspend=True)
    def send_email(to: str) -> str:
        return f"sent to {to}"

    sid = start_session()
    assert sid is not None

    result: list[str] = []
    caught: list[Exception | None] = [None]

    def call() -> None:
        try:
            result.append(send_email("a@b.c"))
        except Exception as e:
            caught[0] = e

    ctx = copy_context()  # contextvar 不随新线程传播，须拷贝当前会话上下文
    thread = threading.Thread(target=ctx.run, args=(call,))
    thread.start()
    decision_id = _poll_pending_decision(server_url, sid)
    resp = httpx.post(f"{server_url}/v1/decisions/{decision_id}/resolve", json={"action": "allow"})
    assert resp.status_code == 200
    thread.join(timeout=5.0)
    assert not thread.is_alive()
    assert caught[0] is None
    assert result == ["sent to a@b.c"]
    end_session()


def test_breakpoint_reject(server_url: str) -> None:
    """suspend 工具命中挂起 → resolve reject → 抛 ToolRejected（走错误分支）。"""

    @bind_tool(suspend=True)
    def send_email(to: str) -> str:
        return f"sent to {to}"

    sid = start_session()
    assert sid is not None

    caught: list[Exception | None] = [None]

    def call() -> None:
        try:
            send_email("a@b.c")
        except Exception as e:
            caught[0] = e

    ctx = copy_context()  # contextvar 不随新线程传播，须拷贝当前会话上下文
    thread = threading.Thread(target=ctx.run, args=(call,))
    thread.start()
    decision_id = _poll_pending_decision(server_url, sid)
    resp = httpx.post(f"{server_url}/v1/decisions/{decision_id}/resolve", json={"action": "reject"})
    assert resp.status_code == 200
    thread.join(timeout=5.0)
    assert not thread.is_alive()
    assert isinstance(caught[0], ToolRejected)
    end_session()


def test_ws_real_handshake(server_url: str) -> None:
    """真实 uvicorn 上 /v1/stream 可握手并收到 session_status。"""
    ws_url = server_url.replace("http://", "ws://") + "/v1/stream"
    with connect(ws_url) as ws:
        time.sleep(0.05)  # 等 hub.connect 完成注册，避免广播早于连接入集合
        resp = httpx.post(f"{server_url}/v1/sessions", json={})
        sid = resp.json()["session_id"]
        evt = json.loads(ws.recv(timeout=5.0))
        assert evt["type"] == "session_status"
        assert evt["session_id"] == sid
        assert evt["status"] == "running"
