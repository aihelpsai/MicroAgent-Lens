# 新增 websockets 依赖支持 WebSocket 实时推送

- 日期：2026-10-17
- 版本：v1.0
- 状态：已确认
- 前置阅读：`docs/design/2026-10-16-通信协议-v0.1.md`（§4 WebSocket）、`lens/server/stream.py`

---

## 背景

`lens serve` 用 uvicorn 启动，`pyproject.toml` 原只声明 `uvicorn>=0.29`（基础版，不含 WebSocket 协议库）。真实运行时 `/v1/stream` 握手失败、返回 404，前端收不到五类实时事件（会话列表 / trace 生长 / 挂起弹框只能靠刷新 HTTP 拉取）。阶段 3 的 WS 测试用 TestClient 走 in-process ASGI、不经过 uvicorn 的 WS 层，故未暴露此问题。

## 正文

`dependencies` 新增运行时依赖 `websockets>=12.0`。uvicorn 启动时检测到 websockets 库即启用 WebSocket 协议支持，`/v1/stream` 恢复正常握手与事件广播。不改任何后端逻辑与协议契约（`openapi.yaml`、`stream.py`、`app.py` 均不变）。

## 决策与权衡

- **方案 A（采用）**：显式新增 `websockets` 依赖。最小补法（即 uvicorn 官方错误提示的两种手动安装之一）；仅引入 WS 协议实现，符合项目「依赖最小化」原则。
- **方案 B（弃）**：改用 `uvicorn[standard]`。会额外引入 httptools / uvloop / watchfiles 等非必要依赖，违背依赖最小化。
