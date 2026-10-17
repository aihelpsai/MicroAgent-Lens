"""lens.cli 测试：serve 自动开浏览器与 --no-browser 开关。"""

import sys

import pytest

from lens import cli


def test_serve_opens_browser_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认（无 --no-browser）：_serve 收到 no_browser=False。"""
    calls: list[tuple[str, int, bool]] = []
    monkeypatch.setattr(cli, "_serve", lambda h, p, nb: calls.append((h, p, nb)))
    monkeypatch.setattr(sys, "argv", ["lens", "serve"])
    cli.main()
    assert calls == [("127.0.0.1", 7878, False)]


def test_serve_no_browser_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """--no-browser：_serve 收到 no_browser=True。"""
    calls: list[tuple[str, int, bool]] = []
    monkeypatch.setattr(cli, "_serve", lambda h, p, nb: calls.append((h, p, nb)))
    monkeypatch.setattr(sys, "argv", ["lens", "serve", "--no-browser"])
    cli.main()
    assert calls == [("127.0.0.1", 7878, True)]


def test_open_browser_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """_open_browser 打开 http://host:port/；通配地址映射 127.0.0.1。"""
    opened: list[str] = []
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: opened.append(url))
    cli._open_browser("127.0.0.1", 7878)
    cli._open_browser("0.0.0.0", 7878)
    assert opened == ["http://127.0.0.1:7878/", "http://127.0.0.1:7878/"]
