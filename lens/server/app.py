"""最小可跑 FastAPI 应用（阶段 1 骨架，业务端点后续阶段实现）。"""

from fastapi import FastAPI

app = FastAPI(title="microagent-lens", version="0.1.0")


@app.get("/")
def root() -> dict[str, str]:
    """根路由：服务存活探针。"""
    return {"service": "microagent-lens", "version": "0.1.0"}


@app.get("/health")
def health() -> dict[str, str]:
    """健康检查。"""
    return {"status": "ok"}
