"""Rerank Provider 协议 —— 与 LLM/Embedding 风格保持一致。"""

from typing import Protocol


class RerankProvider(Protocol):
    """精排接口 —— 输入 query 和候选,返回带分数的重排序结果。"""

    name: str

    async def rerank(
        self, query: str, candidates: list[str], top_k: int | None = None
    ) -> list[tuple[int, float]]:
        """返回 [(原始索引, 归一化分数 0-1)],按分数降序。"""
        ...
