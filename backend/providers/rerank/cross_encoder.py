"""Cross-Encoder rerank 实现 —— 走 sentence-transformers 的 CrossEncoder。

为什么和 LocalBGERerank 分开?
- LocalBGERerank 用 FlagEmbedding,BGE 系列专属优化
- 这里用通用 CrossEncoder 接口,可以挂任何 HuggingFace 兼容的 cross-encoder
  模型(bce-reranker-base / ms-marco-MiniLM / 微调过的中文 reranker / 自训练)
- 切换只改 .env: RERANK_PROVIDER=cross_encoder + RERANK_MODEL=<repo_id>

工作原理:
Cross-encoder 把 (query, doc) 拼成单条输入过 BERT,直接输出相关性分数。
比双塔(bi-encoder)精度高,但推理慢,只用在 rerank 阶段(几十条)。
"""

import asyncio
import math

from app.core import with_latency
from config import settings
from providers.rerank.base import RerankProvider


class CrossEncoderRerank(RerankProvider):
    """通用 cross-encoder rerank —— 模型由 settings.rerank.model 决定。"""

    name = "cross_encoder"

    def __init__(self) -> None:
        self.model_name = settings.rerank.model
        self._model = None

    def _lazy_load(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            # max_length 控制单条 (query, doc) 拼接后的截断,512 通用够用
            self._model = CrossEncoder(self.model_name, max_length=512)
        return self._model

    @with_latency("rerank.cross_encoder")
    async def rerank(
        self, query: str, candidates: list[str], top_k: int | None = None
    ) -> list[tuple[int, float]]:
        if not candidates:
            return []
        model = self._lazy_load()
        pairs = [(query, c) for c in candidates]
        scores = await asyncio.to_thread(model.predict, pairs, show_progress_bar=False)
        # 不同 cross-encoder 输出 logits 范围不同,sigmoid 归一化便于阈值统一
        normalized = [_sigmoid(float(s)) for s in scores]
        indexed = list(enumerate(normalized))
        indexed.sort(key=lambda x: x[1], reverse=True)
        if top_k is not None:
            indexed = indexed[:top_k]
        return indexed


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)
