"""lens 命令行入口：lens serve 启动本地调试看板。"""

import argparse
import threading
import webbrowser
from typing import cast

import uvicorn


def main() -> None:
    """CLI 入口，解析参数并分发子命令。"""
    parser = argparse.ArgumentParser(
        prog="lens",
        description="MicroAgent-Lens：本地自托管的 Agent 运行时调试器",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="启动本地调试看板")
    serve_parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    serve_parser.add_argument("--port", type=int, default=7878, help="监听端口")
    serve_parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")

    args = parser.parse_args()
    command = cast(str, args.command)
    if command == "serve":
        _serve(cast(str, args.host), cast(int, args.port), cast(bool, args.no_browser))
    else:
        parser.error(f"未知命令: {command}")


def _open_browser(host: str, port: int) -> None:
    """打开看板首页；通配监听地址改用 127.0.0.1。"""
    url_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    webbrowser.open(f"http://{url_host}:{port}/")


def _serve(host: str, port: int, no_browser: bool) -> None:
    """用 uvicorn 编程式启动 FastAPI 应用；默认启动后开浏览器。"""
    from lens.server.app import _default_db_path, create_app

    if not no_browser:
        timer = threading.Timer(1.0, _open_browser, args=(host, port))
        timer.daemon = True
        timer.start()
    uvicorn.run(create_app(_default_db_path()), host=host, port=port)
