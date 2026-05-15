"""RAG 公共类型 —— 给 rag 内部和 agent 消费者共用,避免反向依赖 agent。

CLAUDE.md 规则 #4 单向依赖:rag 是底层模块,不准 import agent。
ProductCandidate 作为 RAG 召回的输出类型,本该住在 rag 里。
"""

from typing import Any

from pydantic import BaseModel, Field


class ProductCandidate(BaseModel):
    """检索召回的商品候选 —— 在 RAG/Rerank 阶段流转,Agent 消费。"""

    product_id: int
    title: str
    score: float
    snippet: str = ""
    image_url: str | None = None
    price: float | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
