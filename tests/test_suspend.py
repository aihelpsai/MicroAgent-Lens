"""并发挂起 + 熔断 + end 遗留 pending 的运行期验证。

用 httpx.AsyncClient(transport=ASGITransport(app=...)) + asyncio.create_task 驱动：
所有请求共享同一事件循环，挂起请求的 asyncio.Future 才能被 resolve 唤醒。
每个用例以 asyncio.run(main()) 包裹一个 async 主函数，挂起请求放 create_task，
主协程轮询 pending_decisions 后再 resolve / end。
"""

import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from lens.server.app import create_app


@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    """每个用例独立临时库的 FastAPI 实例。"""
    return create_app(tmp_path / "suspend.db")


async def _make_client(app: FastAPI) -> AsyncClient:
    """构造同进程 ASGI 传输的异步 client。"""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def _create_session(client: AsyncClient) -> str:
    resp = await client.post("/v1/sessions", json={})
    assert resp.status_code == 200
    return str(resp.json()["session_id"])


async def _poll_pending_decision(client: AsyncClient, sid: str) -> str:
    """轮询会话详情的 pending_decisions 直到非空，返回 decision_id。"""
    for _ in range(200):
        detail = (await client.get(f"/v1/sessions/{sid}")).json()
        pending = detail["pending_decisions"]
        if pending:
            return str(pending[0]["decision_id"])
        await asyncio.sleep(0.01)
    raise AssertionError("挂起决策未在 2s 内出现")


async def _case_blocks_then_allow(app: FastAPI) -> None:
    async with await _make_client(app) as client:
        sid = await _create_session(client)
        await client.put("/v1/breakpoints", json={"suspend_tools": ["send_email"]})
        task: asyncio.Task[httpx.Response] = asyncio.create_task(
            client.post(
                "/v1/execution-request",
                json={"session_id": sid, "tool_name": "send_email", "args": {"to": "a@b.c"}},
            )
        )
        decision_id = await _poll_pending_decision(client, sid)
        assert not task.done()
        resolve = await client.post(
            f"/v1/decisions/{decision_id}/resolve", json={"action": "allow"}
        )
        assert resolve.status_code == 200
        result = await task
        body = result.json()
        assert body["decision"] == "allow"
        assert body["reason"] is None
        assert body["decision_id"] == decision_id
        detail = (await client.get(f"/v1/sessions/{sid}")).json()
        assert detail["session"]["status"] == "running"


def test_suspend_blocks_then_allow(app: FastAPI) -> None:
    """挂起请求不返回；resolve(allow) 后返回 allow 且会话恢复 running。"""
    asyncio.run(_case_blocks_then_allow(app))


async def _case_blocks_then_reject(app: FastAPI) -> None:
    async with await _make_client(app) as client:
        sid = await _create_session(client)
        await client.put("/v1/breakpoints", json={"suspend_tools": ["send_email"]})
        task: asyncio.Task[httpx.Response] = asyncio.create_task(
            client.post(
                "/v1/execution-request",
                json={"session_id": sid, "tool_name": "send_email", "args": {"to": "a@b.c"}},
            )
        )
        decision_id = await _poll_pending_decision(client, sid)
        assert not task.done()
        resolve = await client.post(
            f"/v1/decisions/{decision_id}/resolve", json={"action": "reject"}
        )
        assert resolve.status_code == 200
        result = await task
        body = result.json()
        assert body["decision"] == "reject"
        assert body["reason"] == "human"
        assert body["decision_id"] == decision_id
        detail = (await client.get(f"/v1/sessions/{sid}")).json()
        assert detail["session"]["status"] == "running"


def test_suspend_blocks_then_reject(app: FastAPI) -> None:
    """挂起请求不返回；resolve(reject) 后返回 reject:human。"""
    asyncio.run(_case_blocks_then_reject(app))


async def _case_loop_breaker(app: FastAPI) -> None:
    async with await _make_client(app) as client:
        sid = await _create_session(client)
        payload = {"session_id": sid, "tool_name": "search", "args": {"q": "same"}}
        first = await client.post("/v1/execution-request", json=payload)
        second = await client.post("/v1/execution-request", json=payload)
        third = await client.post("/v1/execution-request", json=payload)
        assert first.json()["decision"] == "allow"
        assert second.json()["decision"] == "allow"
        body = third.json()
        assert body["decision"] == "reject"
        assert body["reason"] == "loop"
        assert body["decision_id"]


def test_loop_breaker_reject_loop(app: FastAPI) -> None:
    """同名同参连发 3 次：前两次 allow，第 3 次 reject:loop。"""
    asyncio.run(_case_loop_breaker(app))


async def _case_end_unblocks_pending(app: FastAPI) -> None:
    async with await _make_client(app) as client:
        sid = await _create_session(client)
        await client.put("/v1/breakpoints", json={"suspend_tools": ["send_email"]})
        task: asyncio.Task[httpx.Response] = asyncio.create_task(
            client.post(
                "/v1/execution-request",
                json={"session_id": sid, "tool_name": "send_email", "args": {}},
            )
        )
        decision_id = await _poll_pending_decision(client, sid)
        end_resp = await client.post(f"/v1/sessions/{sid}/end")
        assert end_resp.status_code == 200
        result = await task
        body = result.json()
        assert body["decision"] == "reject"
        assert body["reason"] == "human"
        assert body["decision_id"] == decision_id
        detail = (await client.get(f"/v1/sessions/{sid}")).json()
        assert detail["session"]["status"] == "ended"


def test_end_session_unblocks_pending(app: FastAPI) -> None:
    """end 会话时遗留 pending 被唤醒为 reject:human，会话置 ended。"""
    asyncio.run(_case_end_unblocks_pending(app))
