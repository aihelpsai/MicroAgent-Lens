"""SQLite 数据层：sessions / trace_nodes / decisions 三表 CRUD 与状态流转。

标准库 sqlite3 实现；Store 只持有不可变 db_path，每方法独立连接，无持久连接字段、
无模块级可变状态。
"""

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

SessionStatus = Literal["running", "paused", "ended"]
NodeType = Literal["thought", "tool_call", "tool_result"]
DecisionStatus = Literal["pending", "allowed", "rejected"]
DecisionReason = Literal["loop", "human"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  status     TEXT NOT NULL,           -- running | paused | ended
  created_at TEXT NOT NULL,
  ended_at   TEXT,
  metadata   TEXT                     -- JSON 字符串，可空
);
CREATE TABLE IF NOT EXISTS trace_nodes (
  node_id    TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(session_id),
  type       TEXT NOT NULL,           -- thought | tool_call | tool_result
  parent_id  TEXT REFERENCES trace_nodes(node_id),
  created_at TEXT NOT NULL,
  content    TEXT                     -- JSON 字符串
);
CREATE TABLE IF NOT EXISTS decisions (
  decision_id TEXT PRIMARY KEY,
  session_id  TEXT NOT NULL REFERENCES sessions(session_id),
  tool_name   TEXT NOT NULL,
  args        TEXT NOT NULL,          -- JSON 字符串
  status      TEXT NOT NULL,          -- pending | allowed | rejected
  reason      TEXT,                   -- loop | human，仅 rejected 有值
  created_at  TEXT NOT NULL,
  resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_trace_nodes_session ON trace_nodes(session_id);
CREATE INDEX IF NOT EXISTS idx_decisions_session ON decisions(session_id, status);
"""


@dataclass(frozen=True)
class Session:
    session_id: str
    status: SessionStatus
    created_at: str
    ended_at: str | None
    metadata: dict[str, Any] | None


@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    status: SessionStatus
    created_at: str
    tool_count: int


@dataclass(frozen=True)
class TraceNode:
    node_id: str
    session_id: str
    type: NodeType
    parent_id: str | None
    created_at: str
    content: Any


@dataclass(frozen=True)
class Decision:
    decision_id: str
    session_id: str
    tool_name: str
    args: dict[str, Any]
    status: DecisionStatus
    reason: DecisionReason | None
    created_at: str
    resolved_at: str | None


def _now() -> str:
    """返回当前 UTC 时间戳（ISO 8601）。"""
    return datetime.now(UTC).isoformat()


def _loads_json(text: str | None) -> Any:
    """解析 JSON 文本；None（对应 NULL 列）直接返回 None。"""
    if text is None:
        return None
    return json.loads(text)


def _validate_decision_reason(status: DecisionStatus, reason: DecisionReason | None) -> None:
    """校验 decisions 的 reason 约束：rejected 必须有 loop|human，其余必须为 None。"""
    if status == "rejected":
        if reason not in ("loop", "human"):
            raise ValueError("status='rejected' 时 reason 必须为 'loop' 或 'human'")
    elif reason is not None:
        raise ValueError("非 rejected 状态 reason 必须为 None")


def _validate_session_transition(current: SessionStatus, target: SessionStatus) -> None:
    """校验会话状态流转表：ended 终态无去向，其余按合法边表。"""
    allowed: tuple[SessionStatus, ...]
    if current == "running":
        allowed = ("paused", "ended")
    elif current == "paused":
        allowed = ("running", "ended")
    else:
        allowed = ()
    if target not in allowed:
        raise ValueError(f"非法会话状态流转: {current} -> {target}")


def _session_from_row(row: sqlite3.Row) -> Session:
    return Session(
        session_id=cast(str, row["session_id"]),
        status=cast(SessionStatus, row["status"]),
        created_at=cast(str, row["created_at"]),
        ended_at=cast(str | None, row["ended_at"]),
        metadata=cast(dict[str, Any] | None, _loads_json(row["metadata"])),
    )


def _node_from_row(row: sqlite3.Row) -> TraceNode:
    return TraceNode(
        node_id=cast(str, row["node_id"]),
        session_id=cast(str, row["session_id"]),
        type=cast(NodeType, row["type"]),
        parent_id=cast(str | None, row["parent_id"]),
        created_at=cast(str, row["created_at"]),
        content=_loads_json(row["content"]),
    )


def _decision_from_row(row: sqlite3.Row) -> Decision:
    return Decision(
        decision_id=cast(str, row["decision_id"]),
        session_id=cast(str, row["session_id"]),
        tool_name=cast(str, row["tool_name"]),
        args=cast(dict[str, Any], _loads_json(row["args"])),
        status=cast(DecisionStatus, row["status"]),
        reason=cast(DecisionReason | None, row["reason"]),
        created_at=cast(str, row["created_at"]),
        resolved_at=cast(str | None, row["resolved_at"]),
    )


class Store:
    """SQLite 持久层：持有不可变 db_path，每方法独立连接。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path: str = str(db_path)

    def _connect(self) -> sqlite3.Connection:
        """新建独立连接并启用 sqlite3.Row 行工厂。"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        """建表与索引（全部 IF NOT EXISTS，幂等）。"""
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    # ---- sessions ----

    def create_session(self, session_id: str, metadata: dict[str, Any] | None = None) -> None:
        """新建会话：status='running'，created_at=now，metadata 序列化为 JSON（None 存 NULL）。"""
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, status, created_at, ended_at, metadata) "
                "VALUES (?, ?, ?, NULL, ?)",
                (session_id, "running", _now(), json.dumps(metadata) if metadata is not None else None),
            )
            conn.commit()

    def get_session(self, session_id: str) -> Session | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT session_id, status, created_at, ended_at, metadata FROM sessions "
                "WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return _session_from_row(row)

    def list_sessions(self) -> list[SessionSummary]:
        """按插入序列出会话摘要；tool_count 用子查询统计该会话 tool_call 节点数。"""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT s.session_id, s.status, s.created_at, "
                "(SELECT COUNT(*) FROM trace_nodes t "
                " WHERE t.session_id = s.session_id AND t.type = 'tool_call') AS tool_count "
                "FROM sessions s ORDER BY s.rowid",
            ).fetchall()
        return [
            SessionSummary(
                session_id=cast(str, row["session_id"]),
                status=cast(SessionStatus, row["status"]),
                created_at=cast(str, row["created_at"]),
                tool_count=cast(int, row["tool_count"]),
            )
            for row in rows
        ]

    def set_session_status(self, session_id: str, status: SessionStatus) -> None:
        """流转会话状态：不存在/非法流转抛 ValueError；同状态幂等 no-op；ended 写 ended_at。"""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT status FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"session 不存在: {session_id}")
            current = cast(SessionStatus, row["status"])
            if current == status:
                return
            _validate_session_transition(current, status)
            if status == "ended":
                conn.execute(
                    "UPDATE sessions SET status = 'ended', ended_at = ? WHERE session_id = ?",
                    (_now(), session_id),
                )
            else:
                conn.execute(
                    "UPDATE sessions SET status = ? WHERE session_id = ?",
                    (status, session_id),
                )
            conn.commit()

    # ---- trace_nodes ----

    def add_node(
        self,
        node_id: str,
        session_id: str,
        type: NodeType,
        content: Any,
        parent_id: str | None = None,
    ) -> None:
        """新增 trace 节点：created_at=now，content 序列化为 JSON。"""
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO trace_nodes (node_id, session_id, type, parent_id, created_at, content) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (node_id, session_id, type, parent_id, _now(), json.dumps(content)),
            )
            conn.commit()

    def get_node(self, node_id: str) -> TraceNode | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT node_id, session_id, type, parent_id, created_at, content "
                "FROM trace_nodes WHERE node_id = ?",
                (node_id,),
            ).fetchone()
        if row is None:
            return None
        return _node_from_row(row)

    def list_nodes(self, session_id: str) -> list[TraceNode]:
        """按插入序列出该会话的 trace 节点。"""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT node_id, session_id, type, parent_id, created_at, content "
                "FROM trace_nodes WHERE session_id = ? ORDER BY rowid",
                (session_id,),
            ).fetchall()
        return [_node_from_row(row) for row in rows]

    # ---- decisions ----

    def create_decision(
        self,
        decision_id: str,
        session_id: str,
        tool_name: str,
        args: dict[str, Any],
        status: DecisionStatus = "pending",
        reason: DecisionReason | None = None,
    ) -> None:
        """新建决策：校验 reason 约束；初始即 resolved 时写 resolved_at=now，pending 写 NULL。"""
        _validate_decision_reason(status, reason)
        resolved_at = None if status == "pending" else _now()
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO decisions "
                "(decision_id, session_id, tool_name, args, status, reason, created_at, resolved_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (decision_id, session_id, tool_name, json.dumps(args), status, reason, _now(), resolved_at),
            )
            conn.commit()

    def get_decision(self, decision_id: str) -> Decision | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT decision_id, session_id, tool_name, args, status, reason, created_at, resolved_at "
                "FROM decisions WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
        if row is None:
            return None
        return _decision_from_row(row)

    def transition_decision(
        self,
        decision_id: str,
        status: DecisionStatus,
        reason: DecisionReason | None = None,
    ) -> None:
        """流转决策：仅 pending→allowed/rejected 合法，非法流转抛 ValueError；写 resolved_at。"""
        _validate_decision_reason(status, reason)
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT status FROM decisions WHERE decision_id = ?", (decision_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"decision 不存在: {decision_id}")
            current = cast(DecisionStatus, row["status"])
            if current != "pending":
                raise ValueError(f"非法决策流转: {current} -> {status}")
            if status not in ("allowed", "rejected"):
                raise ValueError(f"非法决策流转: {current} -> {status}")
            conn.execute(
                "UPDATE decisions SET status = ?, reason = ?, resolved_at = ? WHERE decision_id = ?",
                (status, reason, _now(), decision_id),
            )
            conn.commit()

    def list_pending_decisions(self, session_id: str) -> list[Decision]:
        """列出该会话 status='pending' 的决策，按插入序。"""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT decision_id, session_id, tool_name, args, status, reason, created_at, resolved_at "
                "FROM decisions WHERE session_id = ? AND status = 'pending' ORDER BY rowid",
                (session_id,),
            ).fetchall()
        return [_decision_from_row(row) for row in rows]
