# MicroAgent-Lens

Pure Python、零配置、本地自托管的 **Agent 运行时调试器**（runtime debugger）——对标 pdb/gdb，而非 APM。

核心价值是「运行时控制」：死循环熔断（Loop Breaker）+ 人机协同断点（Active Breakpoint）+ trace 树回看。

> 状态：0.1.0 早期开发中。已完成项目框架与 `lens serve` 入口；熔断 / 断点 / trace 等核心能力正按[实现路线](docs/plans/2026-10-17-0.1.0-实现路线.md)推进。

## 快速开始

```bash
# 开发模式安装
pip install -e ".[dev]"

# 启动本地调试看板（默认 http://127.0.0.1:7878）
lens serve
```

起服后浏览器打开 `http://localhost:7878`。

> 要求 Python >= 3.11。

## 目录结构

```
lens/
  sdk/       # 薄协议 client（装饰器 + HTTP client），无决策逻辑
  server/    # FastAPI + 决策引擎 + SQLite，所有智能在此
  webui/     # 静态 HTML/JS 控制面板
openapi.yaml # 通信协议唯一来源（契约）
docs/        # PRD / 设计 / 路线 / plan 文档
tests/       # 测试
```

## 开发命令

```bash
pip install -e ".[dev]"   # 开发模式安装
ruff format .             # 格式化
ruff check .              # lint
mypy lens                 # 类型检查（strict）
pytest                    # 测试
```

## 文档

- 文档索引与编写规范：[docs/index.md](docs/index.md)
- 产品需求：[docs/prd/](docs/prd/)
- 架构决策 / 通信协议：[docs/investigation/](docs/investigation/)、[docs/design/](docs/design/)
- 实现路线与阶段 plan：[docs/plans/](docs/plans/)
