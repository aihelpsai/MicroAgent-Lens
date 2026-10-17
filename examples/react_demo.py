"""MicroAgent-Lens 自研 ReAct 演示 agent（脚本化，无真实 LLM）。

演示三场景（对应路线 §7 验收）：
  degrade     不起看板照常跑（SDK 静默降级）
  loop        起看板，同名同参连发 3 次触发熔断
  breakpoint  起看板，send_email 命中挂起，前端放行/拒绝

用法（无 python 命令，用 .venv/bin/ 前缀）：
  .venv/bin/python examples/react_demo.py --scenario degrade
  .venv/bin/python examples/react_demo.py --scenario loop
  .venv/bin/python examples/react_demo.py --scenario breakpoint

智能全在后端：本 demo 只调 lens 公共 API + 按响应分派，不做熔断/断点/相似度判定。
"""

import argparse

from lens import (
    AgentLoopException,
    ToolRejected,
    bind_tool,
    end_session,
    log_thought,
    start_session,
)


@bind_tool()
def search(query: str) -> str:
    """模拟搜索工具（普通工具）。"""
    return f"搜索结果：{query}"


@bind_tool()
def fetch(url: str) -> str:
    """模拟抓取工具（普通工具）。"""
    return f"已抓取：{url}"


@bind_tool(suspend=True)
def send_email(recipient: str) -> str:
    """模拟发邮件工具（suspend 工具，命中即挂起等人机协同）。"""
    return f"已发送邮件至 {recipient}"


def run_degrade() -> None:
    """降级场景：不起看板照常执行，无异常。"""
    sid = start_session()
    print(f"[degrade] start_session -> {sid}（None 即已降级）")
    print(f"[degrade] search -> {search('hello')}")
    print(f"[degrade] fetch -> {fetch('http://example.com')}")
    end_session()


def run_loop() -> None:
    """熔断场景：同名同参连发 3 次，第 3 次抛 AgentLoopException。"""
    sid = start_session()
    print(f"[loop] start_session -> {sid}")
    for i in range(3):
        try:
            print(f"[loop] 第 {i + 1} 次 search -> {search('相同查询')}")
        except AgentLoopException as e:
            print(f"[loop] 熔断：{e}")
            break
    end_session()


def run_breakpoint() -> None:
    """断点场景：send_email 命中挂起，前端放行/拒绝。"""
    sid = start_session()
    print(f"[breakpoint] start_session -> {sid}")
    log_thought("演示：先搜索，再发邮件（命中挂起）")
    print(f"[breakpoint] search -> {search('hello')}")
    try:
        print(f"[breakpoint] send_email -> {send_email('a@b.c')}")
    except ToolRejected as e:
        print(f"[breakpoint] 被人工拒绝，走错误分支：{e}")
    end_session()


def main() -> None:
    parser = argparse.ArgumentParser(prog="react_demo", description="MicroAgent-Lens ReAct 演示")
    parser.add_argument(
        "--scenario",
        choices=["degrade", "loop", "breakpoint"],
        default="breakpoint",
        help="演示场景",
    )
    args = parser.parse_args()
    if args.scenario == "degrade":
        run_degrade()
    elif args.scenario == "loop":
        run_loop()
    else:
        run_breakpoint()


if __name__ == "__main__":
    main()
