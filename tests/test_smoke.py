"""阶段 1 smoke 测试：最小 app 能启动，根路由与健康检查回 200。"""

from fastapi.testclient import TestClient

from lens.server.app import app

client = TestClient(app)


def test_root_returns_200() -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["service"] == "microagent-lens"


def test_health_returns_ok() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
