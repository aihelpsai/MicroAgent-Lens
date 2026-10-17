"""SQLite 数据层 Store 三表 CRUD 与状态流转测试。"""

from pathlib import Path
from typing import Any

import pytest

from lens.server.store import Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    """每个用例独立临时库（非 :memory:，因每方法独立连接）。"""
    s = Store(tmp_path / "test.db")
    s.init()
    return s


# ---- sessions ----


def test_create_and_get_session_metadata_none(store: Store) -> None:
    store.create_session("s1")
    got = store.get_session("s1")
    assert got is not None
    assert got.session_id == "s1"
    assert got.status == "running"
    assert got.created_at != ""
    assert got.ended_at is None
    assert got.metadata is None


def test_create_and_get_session_metadata_dict(store: Store) -> None:
    store.create_session("s2", metadata={"agent": "demo", "n": 1})
    got = store.get_session("s2")
    assert got is not None
    assert got.metadata == {"agent": "demo", "n": 1}


def test_list_sessions_tool_count(store: Store) -> None:
    store.create_session("s1")
    store.create_session("s2")
    store.add_node("n1", "s1", "tool_call", {"tool": "search"})
    store.add_node("n2", "s1", "tool_call", {"tool": "calc"})
    store.add_node("n3", "s1", "thought", "thinking...")
    summaries = store.list_sessions()
    assert [s.session_id for s in summaries] == ["s1", "s2"]
    by_id = {s.session_id: s for s in summaries}
    assert by_id["s1"].tool_count == 2
    assert by_id["s2"].tool_count == 0


def test_session_status_flow_legal(store: Store) -> None:
    store.create_session("s1")
    store.set_session_status("s1", "paused")
    store.set_session_status("s1", "running")
    store.set_session_status("s1", "ended")
    got = store.get_session("s1")
    assert got is not None
    assert got.status == "ended"
    assert got.ended_at is not None


def test_session_ended_is_terminal(store: Store) -> None:
    store.create_session("s1")
    store.set_session_status("s1", "ended")
    with pytest.raises(ValueError):
        store.set_session_status("s1", "running")


def test_session_same_status_is_noop(store: Store) -> None:
    store.create_session("s1")
    store.set_session_status("s1", "running")
    got = store.get_session("s1")
    assert got is not None and got.status == "running"


def test_get_missing_session_returns_none(store: Store) -> None:
    assert store.get_session("missing") is None


def test_set_status_missing_session_raises(store: Store) -> None:
    with pytest.raises(ValueError):
        store.set_session_status("missing", "paused")


# ---- trace_nodes ----


@pytest.mark.parametrize(
    "content",
    [
        {"a": 1, "b": [1, 2, 3]},
        [1, "two", {"three": 3}],
        "plain string",
    ],
)
def test_add_and_get_node_content_roundtrip(store: Store, content: Any) -> None:
    store.create_session("s1")
    store.add_node("n1", "s1", "tool_call", content)
    got = store.get_node("n1")
    assert got is not None
    assert got.content == content
    assert got.type == "tool_call"
    assert got.session_id == "s1"
    assert got.created_at != ""


def test_list_nodes_insertion_order_and_parent(store: Store) -> None:
    store.create_session("s1")
    store.add_node("n1", "s1", "thought", "root")
    store.add_node("n2", "s1", "tool_call", {"t": 1}, parent_id="n1")
    nodes = store.list_nodes("s1")
    assert [n.node_id for n in nodes] == ["n1", "n2"]
    assert nodes[0].parent_id is None
    assert nodes[1].parent_id == "n1"


def test_get_missing_node_returns_none(store: Store) -> None:
    assert store.get_node("missing") is None


# ---- decisions ----


def test_create_pending_decision_roundtrip(store: Store) -> None:
    store.create_session("s1")
    store.create_decision("d1", "s1", "search", {"q": "x", "n": 1})
    got = store.get_decision("d1")
    assert got is not None
    assert got.decision_id == "d1"
    assert got.session_id == "s1"
    assert got.tool_name == "search"
    assert got.args == {"q": "x", "n": 1}
    assert got.status == "pending"
    assert got.reason is None
    assert got.resolved_at is None
    assert got.created_at != ""


def test_create_rejected_with_reason_sets_resolved_at(store: Store) -> None:
    store.create_session("s1")
    store.create_decision("d1", "s1", "search", {}, status="rejected", reason="loop")
    got = store.get_decision("d1")
    assert got is not None
    assert got.status == "rejected"
    assert got.reason == "loop"
    assert got.resolved_at is not None


def test_create_rejected_missing_reason_raises(store: Store) -> None:
    store.create_session("s1")
    with pytest.raises(ValueError):
        store.create_decision("d1", "s1", "search", {}, status="rejected")


def test_create_allowed_with_reason_raises(store: Store) -> None:
    store.create_session("s1")
    with pytest.raises(ValueError):
        store.create_decision("d1", "s1", "search", {}, status="allowed", reason="loop")


def test_transition_pending_to_allowed(store: Store) -> None:
    store.create_session("s1")
    store.create_decision("d1", "s1", "search", {})
    store.transition_decision("d1", "allowed")
    got = store.get_decision("d1")
    assert got is not None
    assert got.status == "allowed"
    assert got.reason is None
    assert got.resolved_at is not None


def test_transition_pending_to_rejected(store: Store) -> None:
    store.create_session("s1")
    store.create_decision("d1", "s1", "search", {})
    store.transition_decision("d1", "rejected", reason="human")
    got = store.get_decision("d1")
    assert got is not None
    assert got.status == "rejected"
    assert got.reason == "human"
    assert got.resolved_at is not None


def test_transition_to_rejected_missing_reason_raises(store: Store) -> None:
    store.create_session("s1")
    store.create_decision("d1", "s1", "search", {})
    with pytest.raises(ValueError):
        store.transition_decision("d1", "rejected")


def test_transition_terminal_raises(store: Store) -> None:
    store.create_session("s1")
    store.create_decision("d1", "s1", "search", {}, status="allowed")
    with pytest.raises(ValueError):
        store.transition_decision("d1", "rejected", reason="loop")


def test_transition_missing_decision_raises(store: Store) -> None:
    with pytest.raises(ValueError):
        store.transition_decision("missing", "allowed")


def test_list_pending_decisions_only_pending(store: Store) -> None:
    store.create_session("s1")
    store.create_decision("d1", "s1", "a", {}, status="pending")
    store.create_decision("d2", "s1", "b", {}, status="allowed")
    store.create_decision("d3", "s1", "c", {}, status="rejected", reason="loop")
    store.create_decision("d4", "s1", "d", {}, status="pending")
    pending = store.list_pending_decisions("s1")
    assert [d.decision_id for d in pending] == ["d1", "d4"]
