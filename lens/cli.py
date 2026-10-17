"""lens 命令行入口：lens serve 启动本地调试看板。"""

import argparse
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

    args = parser.parse_args()
    command = cast(str, args.command)
    if command == "serve":
        _serve(cast(str, args.host), cast(int, args.port))
    else:
        parser.error(f"未知命令: {command}")


def _serve(host: str, port: int) -> None:
    """用 uvicorn 编程式启动 FastAPI 应用。"""
    from lens.server.app import app

    uvicorn.run(app, host=host, port=port)
