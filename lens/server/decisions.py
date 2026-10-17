"""挂起决策注册表：内存 pending + asyncio.Future 挂起/唤醒。

单事件循环内访问，无需锁；内存态，重启丢失。DecisionOutcome 只载 allow/reject，
挂起唤醒后的最终决策由端点按 outcome 推导 reason。
"""

import asyncio
from typing import Literal

DecisionOutcome = Literal["allow", "reject"]


class DecisionRegistry:
    """挂起决策的 pending 注册表：register 建 Future 挂起，resolve 唤醒。"""

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[DecisionOutcome]] = {}

    def register(self, decision_id: str) -> asyncio.Future[DecisionOutcome]:
        """注册一个挂起决策并返回其 Future（在 async 端点内调用）。"""
        future: asyncio.Future[DecisionOutcome] = asyncio.get_running_loop().create_future()
        self._pending[decision_id] = future
        return future

    def resolve(self, decision_id: str, outcome: DecisionOutcome) -> bool:
        """取出并 set_result 唤醒挂起方；不存在或已 resolved 返回 False。"""
        future = self._pending.pop(decision_id, None)
        if future is None or future.done():
            return False
        future.set_result(outcome)
        return True

    def is_pending(self, decision_id: str) -> bool:
        """查询 decision_id 是否仍在挂起。"""
        return decision_id in self._pending
