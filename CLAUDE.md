# MicroAgent-Lens 项目规范

## 项目定位

Pure Python、零配置、本地自托管的 Agent 运行时调试器（debugger），对标 pdb/gdb 而非 APM。
核心价值是"运行时控制"：死循环熔断（Loop Breaker）+ 人机协同断点（Active Breakpoint）。

## 目录结构

单包 `lens`，职责分三模块，智能只准落在 server：

- `lens/sdk/`：薄协议 client（装饰器 + HTTP client），无决策逻辑。
- `lens/server/`：FastAPI + 决策引擎 + SQLite，所有智能在此。
- `lens/webui/`：静态 HTML/JS，挂到 server。
- `openapi.yaml`：通信协议唯一来源（契约），后端实现必须与之对齐。

## 常用命令

```bash
pip install -e ".[dev]"   # 开发模式安装
ruff format .             # 格式化
ruff check .              # lint
mypy lens                 # 类型检查
pytest                    # 测试
lens serve                # 起后端看板（本地 7878）
```

## 架构不变量（硬规则，任何改动不得违反）

1. **降级保证**：看板未启动/不可达时，SDK 必须静默降级、agent 照常运行，绝不崩溃。需测试覆盖。
2. **智能放后端**：熔断判定、断点决策、滑动窗口、相似度计算全在 server；SDK 只做"发 HTTP + 阻塞等响应 + 抛异常/返回失败"，禁止在 sdk 加决策逻辑。
3. **统一决策端点**：所有工具调用前走 `POST /v1/execution-request`，返回 `allow` / `reject:loop` / `reject:human`。Loop Breaker 与 Breakpoint 不是两个端点。
4. **语义区分**：熔断 = 抛 `AgentLoopException`；断点【拒绝】= 返回失败结果（不抛异常），让 agent 自行走错误分支。
5. **零配置 + 依赖最小化**：无 Docker/Postgres；新增依赖必须记入 `docs/decisions/`。

## 代码实现约定

- **同步优先**：SDK 用同步 httpx 阻塞等响应（无 asyncio.Event / WebSocket）；后端决策引擎为纯同步函数。
- **无全局可变状态**：决策引擎纯函数、无副作用（SQLite 持久化除外）。
- **命名**：类 CamelCase、函数/变量 snake_case、常量 UPPER（由 ruff N 规则 + mypy strict 自动查）。
- **测试**：每个逻辑代码（纯函数 / 决策逻辑 / 协议 handler 等）都要有对应测试脚本，放 `tests/`；如有主动提及需要测试报告，放 `docs/test/`（记录运行结果，非测试代码），否则不生成测试报告。

## 语言规范（本项目专用，覆盖全局默认）

- **中文**：commit message、代码注释、文档、文件名、日志与提示文案。
- **英文**：变量名、函数名、类名、包名、模块名等代码标识符（遵循 PEP 8）。
- 原因：说明性文字给人和 AI 读，用中文；标识符参与 import/调用/工具链，保持英文。

## commit message 格式

```text
<类型>(<范围>): <一句话摘要>

背景：
<说明为什么需要这次改动、解决什么问题或满足什么需求。>

实现：
- <模块或目录>：<说明该模块的具体改动。>
```

类型：feat / fix / docs / refactor / test / chore。范围：如 sdk / server / webui / docs。

## 规范索引

- 文档索引与编写规范：`docs/index.md`
- 文档模板：`docs/template.md`
- 通信协议（设计决策 + 语义）：`docs/design/`
- 架构决策记录（ADR）：`docs/decisions/`（按需创建）
- code review：通用审查走全局 `gstack-review`，项目特定清单 invoke `review` skill（`.claude/skills/review/SKILL.md`），两者互补、都过
- 本文件与 `AGENTS.md` 内容一致，后者供其他 AI 工具读取。

## 工作方式

本项目代码与文档大部分由 AI 生成。规范优先级：确定性门禁（ruff / mypy / pytest）> 本文件不变量 > 散文规范。详细开发流程见全局 prefs 与 `.claude/skills/`。

**规则与知识分开存放**：知识（是什么 / 为什么）放 `docs/`；规则（怎么做 / 禁止什么 / 检查什么）放本文件（常驻）或 `.claude/skills/`（按需，对应任务时 invoke）。不把规则写成 docs 文档。
