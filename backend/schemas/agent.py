"""Agent / SSE 流事件 schema —— 前端按 type 渲染不同 UI。

前端拿到的事件流大概是:
    data: {"type": "state_change", "state": "intent"}
    data: {"type": "tool_output", "state": "retrieve", "data": {"count": 5}}
    data: {"type": "token", "data": "你好"}
    data: {"type": "done", "data": {"answer": "..."}}

把这些定义清楚,前端 TS 能直接生成类型(用 openapi 或 zod-from-pydantic 都行)。
"""

from typing import Any, Literal

from pydantic import Field

from schemas.common import APIModel


# 事件类型与 agent.AgentEvent.type 对齐
EventType = Literal["state_change", "tool_output", "token", "error", "done"]
# 状态名与 agent.AgentState 对齐(用字符串避免循环依赖)
AgentStateName = Literal[
    "intent",
    "image_understand",
    "query_rewrite",
    "retrieve",
    "rerank",
    "need_clarify",
    "respond",
    "end",
]


class AgentStreamEvent(APIModel):
    """SSE 单帧 schema —— 与 agent.AgentEvent 一一对应,这里是对外契约。"""

    type: EventType
    state: AgentStateName | None = None
    data: Any = None


class ProductCard(APIModel):
    """候选商品卡片 —— 在 tool_output 阶段提前推给前端,提升体验。"""

    product_id: int
    title: str
    score: float
    price: float | None = None
    image_url: str | None = None
    snippet: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)
