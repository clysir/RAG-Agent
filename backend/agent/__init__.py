"""Agent 包入口 —— 暴露核心类型和便捷函数。

当前唯一实现是 ShoppingAgent(自研状态机),BaseAgent 为未来多 Agent 协作预留接口。
"""

from agent.base import BaseAgent
from agent.context import AgentContext, AgentEvent, AgentState, IntentType, ProductCandidate
from agent.state_machine import Agent, new_trace_id, stream_agent

# 给"主导购 Agent"一个语义化的别名,方便未来引入其它 Agent 时区分
ShoppingAgent = Agent

__all__ = [
    "BaseAgent",
    "Agent",
    "ShoppingAgent",
    "AgentContext",
    "AgentEvent",
    "AgentState",
    "IntentType",
    "ProductCandidate",
    "stream_agent",
    "new_trace_id",
]
