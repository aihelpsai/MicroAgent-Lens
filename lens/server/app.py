"""FastAPI 应用工厂：装配 store/decisions/hub/breakpoints 与 8 端点（10 操作）+ WS + 静态挂载。

create_app(db_path) 返回装配完成的 FastAPI 实例；运行时状态全部挂 app.state，
无模块级可变单例。决策判定只编排 loop_breaker.should_break / breakpoint.is_suspended，
端点内不重写判定逻辑。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from lens.server.breakpoint import is_suspended
from lens.server.decisions import DecisionRegistry
from lens.server.loop_breaker import ToolCall, should_break
from lens.server.store import Decision, DecisionReason, Session, SessionSummary, Store, TraceNode
from lens.server.stream import StreamHub


@dataclass
class BreakpointConfig:
    """断点配置内存态（不落 SQLite，重启回默认值）。"""

    suspend_tools: list[str] = field(default_factory=list)
    window_size: int = 3
    similarity_threshold: float = 0.9


class SessionCreate(BaseModel):
    metadata: dict[str, Any] | None = None


class ExecutionRequest(BaseModel):
    session_id: str
    tool_name: str
    args: dict[str, Any]


class ToolResult(BaseModel):
    session_id: str
    tool_name: str
    ok: bool
    result: Any | None = None
    error: str | None = None
    duration_ms: int | None = None


class Thought(BaseModel):
    session_id: str
    content: str


class LoopBreakerConfig(BaseModel):
    window_size: int = 3
    similarity_threshold: float = 0.9


class BreakpointConfigUpdate(BaseModel):
    suspend_tools: list[str] | None = None
    loop_breaker: LoopBreakerConfig | None = None


class ResolveRequest(BaseModel):
    action: Literal["allow", "reject"]


def _session_dict(s: Session) -> dict[str, Any]:
    return {
        "session_id": s.session_id,
        "status": s.status,
        "created_at": s.created_at,
        "ended_at": s.ended_at,
        "metadata": s.metadata,
    }


def _summary_dict(s: SessionSummary) -> dict[str, Any]:
    return {
        "session_id": s.session_id,
        "status": s.status,
        "created_at": s.created_at,
        "tool_count": s.tool_count,
        "token_usage": 0,
    }


def _node_dict(n: TraceNode) -> dict[str, Any]:
    # 注意：openapi TraceNode 无 session_id。
    return {
        "node_id": n.node_id,
        "type": n.type,
        "parent_id": n.parent_id,
        "created_at": n.created_at,
        "content": n.content,
    }


def _node_event_dict(session_id: str, n: TraceNode) -> dict[str, Any]:
    # WS node_added 的 node 含 session_id（全局流按会话归组），区别于 HTTP 的 _node_dict。
    return {
        "node_id": n.node_id,
        "type": n.type,
        "parent_id": n.parent_id,
        "created_at": n.created_at,
        "content": n.content,
        "session_id": session_id,
    }


def _decision_summary_dict(d: Decision) -> dict[str, Any]:
    return {
        "decision_id": d.decision_id,
        "session_id": d.session_id,
        "tool_name": d.tool_name,
        "args": d.args,
        "created_at": d.created_at,
    }


def _breakpoints_dict(c: BreakpointConfig) -> dict[str, Any]:
    return {
        "suspend_tools": c.suspend_tools,
        "loop_breaker": {
            "window_size": c.window_size,
            "similarity_threshold": c.similarity_threshold,
        },
    }


def _not_found(msg: str) -> JSONResponse:
    # openapi NotFound 用 error 键，不用 HTTPException 的 detail。
    return JSONResponse(status_code=404, content={"error": msg})


def _default_db_path() -> Path:
    return Path.home() / ".lens" / "lens.db"


def create_app(db_path: str | Path) -> FastAPI:
    """装配 FastAPI 实例：建库目录 + Store.init，挂运行时状态，注册路由与静态挂载。"""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    store = Store(path)
    store.init()
    app = FastAPI(title="microagent-lens", version="0.1.0")
    app.state.store = store
    app.state.decisions = DecisionRegistry()
    app.state.hub = StreamHub()
    app.state.breakpoints = BreakpointConfig()
    _register_routes(app)
    return app


def _register_routes(app: FastAPI) -> None:
    """注册全部路由；静态挂载位最后挂到 "/"，服务 lens/webui/index.html 占位。"""

    @app.get("/health")
    def health() -> dict[str, str]:
        """健康检查。"""
        return {"status": "ok"}

    @app.post("/v1/sessions", response_model=None)
    async def create_session(request: Request, body: SessionCreate | None = None) -> dict[str, Any]:
        """创建调试会话，广播 session_status(running)。"""
        store = cast(Store, request.app.state.store)
        hub = cast(StreamHub, request.app.state.hub)
        session_id = str(uuid4())
        store.create_session(session_id, body.metadata if body else None)
        await hub.broadcast(
            {"type": "session_status", "session_id": session_id, "status": "running"}
        )
        return _session_dict(cast(Session, store.get_session(session_id)))

    @app.get("/v1/sessions")
    def list_sessions(request: Request) -> dict[str, Any]:
        """会话概要列表。"""
        store = cast(Store, request.app.state.store)
        return {"sessions": [_summary_dict(s) for s in store.list_sessions()]}

    @app.get("/v1/sessions/{session_id}", response_model=None)
    def get_session_detail(session_id: str, request: Request) -> dict[str, Any] | JSONResponse:
        """会话详情 + trace 树 + 待处理决策。"""
        store = cast(Store, request.app.state.store)
        session = store.get_session(session_id)
        if session is None:
            return _not_found(f"session 不存在: {session_id}")
        return {
            "session": _session_dict(session),
            "trace": [_node_dict(n) for n in store.list_nodes(session_id)],
            "pending_decisions": [
                _decision_summary_dict(d) for d in store.list_pending_decisions(session_id)
            ],
        }

    @app.post("/v1/sessions/{session_id}/end", response_model=None)
    async def end_session(session_id: str, request: Request) -> dict[str, Any] | JSONResponse:
        """结束会话：先处理遗留 pending（决策 13）再置 ended，广播 session_status(ended)。"""
        store = cast(Store, request.app.state.store)
        decisions = cast(DecisionRegistry, request.app.state.decisions)
        hub = cast(StreamHub, request.app.state.hub)
        session = store.get_session(session_id)
        if session is None:
            return _not_found(f"session 不存在: {session_id}")
        for d in store.list_pending_decisions(session_id):
            store.transition_decision(d.decision_id, "rejected", reason="human")
            decisions.resolve(d.decision_id, "reject")
        store.set_session_status(session_id, "ended")
        await hub.broadcast({"type": "session_status", "session_id": session_id, "status": "ended"})
        return _session_dict(cast(Session, store.get_session(session_id)))

    @app.post("/v1/execution-request", response_model=None)
    async def execution_request(
        request: Request, body: ExecutionRequest
    ) -> dict[str, Any] | JSONResponse:
        """统一决策端点：①熔断 ②挂起（长挂）③放行。"""
        store = cast(Store, request.app.state.store)
        decisions = cast(DecisionRegistry, request.app.state.decisions)
        hub = cast(StreamHub, request.app.state.hub)
        config = cast(BreakpointConfig, request.app.state.breakpoints)
        session_id = body.session_id
        tool_name = body.tool_name
        args = body.args

        session = store.get_session(session_id)
        if session is None:
            return _not_found(f"session 不存在: {session_id}")
        if session.status == "ended":
            return _not_found(f"session 已结束: {session_id}")

        recent = [
            ToolCall(cast(str, c["tool_name"]), cast(dict[str, Any], c["args"]))
            for c in (
                cast(dict[str, Any], n.content)
                for n in store.list_nodes(session_id)
                if n.type == "tool_call"
            )
        ][-(config.window_size - 1) :]
        current = ToolCall(tool_name, args)

        # ① 熔断：连续同名同参凑满窗口即拒。
        if should_break(recent, current, config.window_size, config.similarity_threshold):
            decision_id = str(uuid4())
            store.create_decision(
                decision_id, session_id, tool_name, args, status="rejected", reason="loop"
            )
            node_id = str(uuid4())
            store.add_node(node_id, session_id, "tool_call", {"tool_name": tool_name, "args": args})
            node = store.get_node(node_id)
            await hub.broadcast(
                {
                    "type": "loop_alert",
                    "session_id": session_id,
                    "tool_name": tool_name,
                    "args": args,
                    "decision_id": decision_id,
                    "created_at": cast(TraceNode, node).created_at,
                }
            )
            await hub.broadcast(
                {
                    "type": "node_added",
                    "session_id": session_id,
                    "node": _node_event_dict(session_id, cast(TraceNode, node)),
                }
            )
            return {"decision": "reject", "reason": "loop", "decision_id": decision_id}

        # ② 挂起：命中 suspend 名单则长挂等待 resolve。
        if is_suspended(tool_name, config.suspend_tools):
            decision_id = str(uuid4())
            store.create_decision(decision_id, session_id, tool_name, args, status="pending")
            node_id = str(uuid4())
            store.add_node(node_id, session_id, "tool_call", {"tool_name": tool_name, "args": args})
            store.set_session_status(session_id, "paused")
            node = store.get_node(node_id)
            decision = store.get_decision(decision_id)
            await hub.broadcast(
                {
                    "type": "node_added",
                    "session_id": session_id,
                    "node": _node_event_dict(session_id, cast(TraceNode, node)),
                }
            )
            await hub.broadcast(
                {
                    "type": "decision_pending",
                    "decision": _decision_summary_dict(cast(Decision, decision)),
                }
            )
            await hub.broadcast(
                {"type": "session_status", "session_id": session_id, "status": "paused"}
            )
            outcome = await decisions.register(decision_id)
            if outcome == "allow":
                return {"decision": "allow", "reason": None, "decision_id": decision_id}
            return {"decision": "reject", "reason": "human", "decision_id": decision_id}

        # ③ 放行。
        node_id = str(uuid4())
        store.add_node(node_id, session_id, "tool_call", {"tool_name": tool_name, "args": args})
        node = store.get_node(node_id)
        await hub.broadcast(
            {
                "type": "node_added",
                "session_id": session_id,
                "node": _node_event_dict(session_id, cast(TraceNode, node)),
            }
        )
        return {"decision": "allow", "reason": None, "decision_id": str(uuid4())}

    @app.post("/v1/tool-result", response_model=None)
    async def record_tool_result(
        request: Request, body: ToolResult
    ) -> dict[str, Any] | JSONResponse:
        """记录工具结果（Observation），广播 node_added(tool_result)。"""
        store = cast(Store, request.app.state.store)
        hub = cast(StreamHub, request.app.state.hub)
        if store.get_session(body.session_id) is None:
            return _not_found(f"session 不存在: {body.session_id}")
        node_id = str(uuid4())
        store.add_node(
            node_id,
            body.session_id,
            "tool_result",
            {
                "tool_name": body.tool_name,
                "ok": body.ok,
                "result": body.result,
                "error": body.error,
                "duration_ms": body.duration_ms,
            },
        )
        node = store.get_node(node_id)
        await hub.broadcast(
            {
                "type": "node_added",
                "session_id": body.session_id,
                "node": _node_event_dict(body.session_id, cast(TraceNode, node)),
            }
        )
        return {}

    @app.post("/v1/thought", response_model=None)
    async def record_thought(request: Request, body: Thought) -> dict[str, Any] | JSONResponse:
        """记录 Thought，广播 node_added(thought)。"""
        store = cast(Store, request.app.state.store)
        hub = cast(StreamHub, request.app.state.hub)
        if store.get_session(body.session_id) is None:
            return _not_found(f"session 不存在: {body.session_id}")
        node_id = str(uuid4())
        store.add_node(node_id, body.session_id, "thought", body.content)
        node = store.get_node(node_id)
        await hub.broadcast(
            {
                "type": "node_added",
                "session_id": body.session_id,
                "node": _node_event_dict(body.session_id, cast(TraceNode, node)),
            }
        )
        return {}

    @app.get("/v1/breakpoints")
    def get_breakpoints(request: Request) -> dict[str, Any]:
        """读取断点配置。"""
        return _breakpoints_dict(cast(BreakpointConfig, request.app.state.breakpoints))

    @app.put("/v1/breakpoints")
    def update_breakpoints(request: Request, body: BreakpointConfigUpdate) -> dict[str, Any]:
        """更新断点配置：suspend_tools 提供则覆盖否则清空；loop_breaker 提供则覆盖否则回默认。"""
        config = cast(BreakpointConfig, request.app.state.breakpoints)
        config.suspend_tools = list(body.suspend_tools) if body.suspend_tools is not None else []
        if body.loop_breaker is not None:
            config.window_size = body.loop_breaker.window_size
            config.similarity_threshold = body.loop_breaker.similarity_threshold
        else:
            config.window_size = 3
            config.similarity_threshold = 0.9
        return _breakpoints_dict(config)

    @app.post("/v1/decisions/{decision_id}/resolve", response_model=None)
    async def resolve_decision(
        decision_id: str, request: Request, body: ResolveRequest
    ) -> dict[str, Any] | JSONResponse:
        """放行/拒绝挂起决策；404 依据 DB 的 status，非 registry 返回值。"""
        store = cast(Store, request.app.state.store)
        decisions = cast(DecisionRegistry, request.app.state.decisions)
        hub = cast(StreamHub, request.app.state.hub)
        decision = store.get_decision(decision_id)
        if decision is None:
            return _not_found(f"decision 不存在: {decision_id}")
        if decision.status != "pending":
            return _not_found(f"decision 已处理: {decision_id}")
        reason: DecisionReason | None = "human" if body.action == "reject" else None
        store.transition_decision(
            decision_id, "allowed" if body.action == "allow" else "rejected", reason=reason
        )
        if not store.list_pending_decisions(decision.session_id):
            store.set_session_status(decision.session_id, "running")
        decisions.resolve(decision_id, body.action)
        session = store.get_session(decision.session_id)
        await hub.broadcast(
            {
                "type": "decision_resolved",
                "decision_id": decision_id,
                "decision": body.action,
                "reason": reason,
            }
        )
        await hub.broadcast(
            {
                "type": "session_status",
                "session_id": decision.session_id,
                "status": cast(Session, session).status,
            }
        )
        return {"decision": body.action, "reason": reason, "decision_id": decision_id}

    @app.websocket("/v1/stream")
    async def stream(ws: WebSocket) -> None:
        """事件流：连接后持续 receive_text 作占位心跳，断开即剔除。"""
        hub = cast(StreamHub, ws.app.state.hub)
        await hub.connect(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            hub.disconnect(ws)

    # 静态挂载位：最后挂到 "/"，服务 lens/webui/index.html 占位（阶段 5 再实现面板）。
    webui_dir = Path(__file__).resolve().parent.parent / "webui"
    app.mount("/", StaticFiles(directory=webui_dir, html=True), name="webui")
