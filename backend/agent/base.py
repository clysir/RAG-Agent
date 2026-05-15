"""Agent 基类协议 —— 为未来多 Agent 协作留接口。

设计思路:
- 当前唯一实现是 ShoppingAgent(自研状态机,在 state_machine.py)
- 未来可能拆出 RouterAgent / ConsultantAgent / CompareAgent / AfterSalesAgent
- 拆分时机:任何单一 Agent 太复杂、prompt 已经超长、状态太多时

多 Agent 协作的常见模式:
1. Router 模式: 一个总控 Agent 决定把请求路由给哪个专家 Agent
2. Pipeline 模式: Agent 串成流水线,前一个的输出是后一个的输入
3. Tool 模式: 子 Agent 暴露成 Tool 给主 Agent 调用(最灵活)

我们目前用单状态机就够,这里只先把抽象立起来,真要拆分时直接 plug。
"""

from typing import AsyncIterator, Protocol

from agent.context import AgentContext, AgentEvent


class BaseAgent(Protocol):
    """Agent 统一接口 —— 所有 Agent 都遵循 stream-of-events 协议。"""

    name: str

    async def run(self, ctx: AgentContext) -> AsyncIterator[AgentEvent]:
        """运行 Agent,异步逐事件吐出。

        事件类型见 schemas.agent.AgentStreamEvent。
        Agent 内部状态切换、工具调用、token 流都通过这一个迭代器对外暴露。
        """
        ...
