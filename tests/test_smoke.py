"""阶段 3 smoke 测试：create_app 工厂装配，根路由服务 webui HTML，健康检查回 200。"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lens.server.app import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """每个用例独立临时库的 TestClient。"""
    with TestClient(create_app(tmp_path / "smoke.db")) as c:
        yield c


def test_root_returns_200(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "MicroAgent-Lens" in resp.text


def test_health_returns_ok(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
