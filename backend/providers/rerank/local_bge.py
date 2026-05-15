"""本地 BGE Reranker —— bge-reranker-v2-m3。

注意分数归一化:
- BGE reranker 输出 logits,数值范围不定;sigmoid 归一化到 0-1 便于阈值过滤
- 业务侧的 RAG_SCORE_THRESHOLD 是基于归一化后的分数(默认 0.3)
"""

import asyncio
import math

from app.core import with_latency
from config import settings
from providers.rerank.base import RerankProvider


class LocalBGERerank(RerankProvider):
    """本地 bge-reranker-v2-m3,首次调用懒加载模型。"""

    name = "local_bge"

    def __init__(self) -> None:
        self.model_name = settings.rerank.model
        self._reranker = None

    def _lazy_load(self):
        if self._reranker is None:
            from FlagEmbedding import FlagReranker

            # use_fp16 显存友好,CPU 自动忽略
            self._reranker = FlagReranker(self.model_name, use_fp16=True)
        return self._reranker

    @with_latency("rerank.local_bge")
    async def rerank(
        self, query: str, candidates: list[str], top_k: int | None = None
    ) -> list[tuple[int, float]]:
        if not candidates:
            return []
        model = self._lazy_load()
        pairs = [[query, c] for c in candidates]
        # 同步推理丢线程池
        scores = await asyncio.to_thread(model.compute_score, pairs, normalize=False)
        if isinstance(scores, float):
            scores = [scores]
        # sigmoid 归一化到 0-1,便于阈值统一
        normalized = [(_sigmoid(s)) for s in scores]
        indexed = list(enumerate(normalized))
        indexed.sort(key=lambda x: x[1], reverse=True)
        if top_k is not None:
            indexed = indexed[:top_k]
        return indexed


def _sigmoid(x: float) -> float:
    # 数值稳定的 sigmoid
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)
