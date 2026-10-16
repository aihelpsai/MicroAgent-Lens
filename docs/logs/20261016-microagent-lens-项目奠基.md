# 工作日志：项目奠基（首日）

**概述**

1. 需求：MicroAgent-Lens 项目第一天奠基——从零初始化仓库，并落地 PRD、规范体系、工具链、通信协议契约四块基础设施，收尾时补齐项目级 `log-generate` skill。
2. 结果：5 个 commit 已提交（`3a92894` → `8f17ed9`，均在 main）；本对话新增的 `.claude/skills/log-generate/` 与 `docs/logs/` 日志**未提交**。
3. 状态：代码/文档门禁（ruff/mypy/pytest）尚未跑到，因 SDK/server 实现代码尚未开写，属预期。

**前置需求**

无前置，今天为项目首次启动（首个 commit `3a92894`，15:29）。

**工作内容**

按提交顺序（均为 2026-10-16）：

1. **初始化仓库** `3a92894` — `chore: init`：建立 git 仓库，落地 `.gitignore` 与根目录 `prd.md`（产品需求初稿）。
2. **迁移 PRD + 定位架构决策** `8179725` — `docs(prd)`：根目录 `prd.md` 单文件不便分类管理，迁移为 `docs/prd/` 下日期前缀命名的文档（完整版 v0.0.1 与简略版初稿），并新增 `docs/investigation/` 定位与架构决策纪要（差异化定位、智能放后端、统一决策端点），删除根目录 `prd.md`。
3. **建立 AI 开发规范体系** `49243df` — `docs(规范)`：本项目代码与文档大部分由 AI 生成，将规范固化为 AI 可执行的确定性约束。落地 `CLAUDE.md`/`AGENTS.md`（定位、架构不变量、代码实现约定、语言规范、commit 格式）、`docs/index.md`（文档唯一入口）、`docs/template.md`（文档模板）、`.claude/skills/review/`（项目特定 code review 清单）。
4. **配置工具链** `dbf6d67` — `chore(工具链)`：规范优先由确定性门禁执行。`pyproject.toml` 定义单包 `lens`、ruff 与 mypy strict、pytest；`.gitignore` 补充 mypy/ruff 缓存、SQLite 库文件、本地 Claude 设置。
5. **定义协议契约** `8f17ed9` — `feat(协议)`：协议是后端与 SDK、未来跨语言 SDK 的唯一契约，先于实现确定。`openapi.yaml` 给出 8 路径 / 9 schema 完整契约；`docs/design/` 记录通信协议设计决策与关键语义（决策流程、挂起机制、降级、WebSocket 事件）。
6. **新增 log-generate skill**（本对话，未提交）：参考全局 `/log-generate`，唯一区别是工作日志落盘目录改为本项目 `docs/logs/`，据此产出本文件。

**改动文件**

| 提交 | 文件 | 变更点 |
| --- | --- | --- |
| `3a92894` | `.gitignore` | 新增，基础忽略规则 |
| `3a92894` | `prd.md` | 新增，产品需求初稿（后被迁移删除） |
| `8179725` | `docs/investigation/2026-10-16-定位与架构决策.md` | 新增，定位与架构决策纪要 |
| `8179725` | `docs/prd/2026-10-16-项目v0.0.1.md` | 新增，PRD 完整版 |
| `8179725` | `docs/prd/2026-10-16-项目v0.0.1（简略）.md` | 新增，PRD 简略版 |
| `8179725` | `prd.md` | 删除 |
| `49243df` | `.claude/skills/review/SKILL.md` | 新增，项目 code review 清单 |
| `49243df` | `AGENTS.md` / `CLAUDE.md` | 新增，项目规范（内容一致） |
| `49243df` | `docs/index.md` / `docs/template.md` | 新增，文档入口与模板 |
| `dbf6d67` | `pyproject.toml` | 新增，单包 `lens` + ruff/mypy/pytest 配置 |
| `dbf6d67` | `.gitignore` | 补充 mypy/ruff 缓存、SQLite、本地 Claude 设置 |
| `8f17ed9` | `openapi.yaml` | 新增，8 路径 / 9 schema 契约 |
| `8f17ed9` | `docs/design/2026-10-16-通信协议-v0.1.md` | 新增，协议设计决策与关键语义 |
| 未提交 | `.claude/skills/log-generate/SKILL.md` | 新增，项目级 log-generate skill（目录指向 `docs/logs/`） |
| 未提交 | `docs/logs/20261016-microagent-lens-项目奠基.md` | 新增，本工作日志 |

**出现的问题与结论**

| # | 问题 | 根因 | 结论·解法 |
| --- | --- | --- | --- |
| 1 | 全局与项目存在同名 `log-generate` skill，本 session 的 skill 列表仍显示全局版 description（wisepool 目录） | skill 列表在本 session 启动时已快照，新增项目 skill 后未刷新 | 项目级 skill 应优先于全局同名；需新 session 验证实际落盘目录是否走项目版，若仍走全局版则排查加载优先级或改名去冲突 |
| 2 | `docs/logs/` 空目录不会被 git 跟踪 | git 只跟踪文件，不跟踪空目录 | 已解决：本次日志落盘后目录即有内容，无需 `.gitkeep` |
| 3 | 首日提交作者不一致：`3a92894` 为 `yumengqin <yumengqin@wisepool.com.cn>`，其余为 `yu <773313304@qq.com>` | git 用户配置差异（init 由另一身份执行） | 待确认：若后续统一由 `yu` 提交，无需处理；若需统一署名历史，可 `git filter-repo` 重写（非必要不动） |

**续接指引**

- 待办：`git add .claude/skills/log-generate docs/logs` 后 commit，类型建议 `feat(skill)`，按项目 commit 格式（类型(范围)+一句话摘要+背景/实现两节）补齐。
- 下一步：契约已定，开始实现 SDK / server / webui 三模块——建议从 `lens/server`（决策引擎 + FastAPI + SQLite）或 `lens/sdk`（薄协议 client）起步，实现须逐条对齐 `openapi.yaml` 与 `.claude/skills/review/` 清单（降级保证、智能放后端、统一决策端点、语义区分四条不变量）。
- 门禁：实现代码落地后跑 `pip install -e ".[dev]"` → `ruff check .` / `mypy lens` / `pytest`，架构不变量对应的降级/熔断/断点语义需有测试覆盖。
- 验证 log-generate 生效：新 session 触发「生成 log」，确认落盘目录为本项目 `docs/logs/` 而非全局 wisepool 目录。
- 环境终态：分支 `main`，仅 `.claude/skills/log-generate/` 与 `docs/logs/` 两个 untracked 项，无依赖变更、无代码实现。
