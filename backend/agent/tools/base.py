"""Tool 协议 —— 所有 Agent 工具的统一接口。

设计原则:
- 每个 Tool 只负责一件事(单一职责),读写 AgentContext
- execute() 是协程,内部可以再调 LLM / 检索 / 数据库
- 返回值用于状态机判断下一状态,主要数据写回 ctx
"""

from typing import Any, Protocol

from agent.context import AgentContext


class Tool(Protocol):
    """所有工具必须实现的接口。"""

    name: str

    async def execute(self, ctx: AgentContext) -> Any:
        """执行工具逻辑 —— 修改 ctx,可选返回供状态机决策的摘要信息。"""
        ...
