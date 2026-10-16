
1. 产品概述与定位


1.1 背景与痛点

在开发复杂的 LLM Agent（特别是具备 ReAct 循环或多智能体协同系统）时，开发者面临两大核心痛点：
• 被动观测的无奈（“盲飞”）：传统 APM（如 Langfuse、Langsmith）架构过重，需要 Docker/Postgres。且只能在 Agent 跑完后进行被动查看，无法阻止 Agent 运行时陷入死循环（Loop）导致 Token 费用暴涨。
• 高危工具调用失控：在本地调试涉及写数据库、发邮件、调用金融 API 等高危工具时，开发者不敢用真实环境测试，缺乏一种像传统编程语言（Java/Go）一样的“断点（Breakpoint）”控制机制。


1.2 产品定位

MicroAgent-Lens 是一款专为 Agent 开发者打造的 Pure Python、零配置、本地自托管的 Agent 智能体调试工作台（Debugger）。
• 核心口号：Stop tracing after crashes. Control your agents in real-time. (告别崩溃后的追溯，实时掌控你的智能体。)


2. 核心功能需求 (Features)

MVP 版本聚焦于三个核心模块：极致轻量级接入、实时主动拦截机制、Agent 专属思维轨迹看板。


模块一：Zero-Config SDK 探针

• 【需求描述】 开发者通过一行代码或命令行，即可无侵入地拦截大模型（LLM）的输入输出及工具调用。
• 【具体规则】
	• 支持以 Python 装饰器（Decorator）形式挂载到自定义工具函数上：@lens.bind_tool()。
	• 自动管理 Session 状态，利用 Python 的 contextvars 维持多线程/异步环境下的 Trace 树状上下级关系。
	• 免部署设计：SDK 收集的数据直接通过本地 IPC 或异步 HTTP 发送给本地轻量存储，不需要用户配置任何外部数据库。


模块二：Active Guardrails（主动防御与断点引擎）

这是本项目的核心技术壁垒与面试亮点。

1. 滑窗状态死循环熔断器 (Loop Breaker)

• 原理：SDK 内部维护一个滑动窗口，记录当前 Session 最近 N 次的 Action (工具名) 和 Arguments (参数)。
• 规则：若连续 3 次调用的工具名称完全一致，且参数的文本相似度（如编辑距离或 Jaccard 相似度）大于 90%，触发熔断拦截。
• 动作：SDK 强行中断 LLM 轮询，向主程序抛出自定义异常 AgentLoopException，防止 Token 持续空转烧钱。



2. 人机协同高危断点拦截 (Active Breakpoint)

• 原理：基于 WebSocket 的双向通信阻塞机制。
• 规则：开发者可在前端 UI 或配置文件中，将特定工具（如 execute_sql, send_email）标记为 SUSPEND（暂停）。
• 动作：
	1. 当 Agent 命中该工具时，SDK 拦截执行，通过 WebSocket 向 WebUI 发送挂起信号。
	2. SDK 内部使用异步事件（asyncio.Event）阻塞当前执行线程。
	3. 网页端弹出交互框，显示当前的 Prompt、准备调用的工具及参数。
	4. 开发者在网页端点击【放行】或【拒绝】后，网页向 SDK 回传控制信号，SDK 解除阻塞继续执行。


模块三：Local Visual Dashboard（本地可视化工作台）

• 【需求描述】 一个纯 Python 编写的极简、高颜值暗黑模式仪表盘。
• 【具体规则】
	• 主页/列表页：展示历史调试的 Session 列表、成功/失败状态、Token 总消耗、运行耗时。
	• 轨迹详情页（Agent Trace Tree）：专门优化 ReAct 结构的树状视图。清晰区分 Thought (思考) -> Action (工具调用) -> Observation (工具返回)。
	• 断点控制面板：提供开关，允许动态勾选哪些工具需要开启“执行前暂停”断点。
