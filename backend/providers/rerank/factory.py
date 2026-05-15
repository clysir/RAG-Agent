"""Rerank 工厂 —— 根据 settings.rerank.provider 选实现。

支持的 provider:
- none: 不做精排(NoOp),链路验证或资源紧时用
- local_bge: BGE 系列,FlagEmbedding 加载,中英文强
- cross_encoder: 通用 cross-encoder,sentence-transformers 加载,
                 可挂任意 HuggingFace 兼容 reranker(bce-reranker / MiniLM / 自训)

所有实现都返回 sigmoid 归一化后的分数(0-1),配合 RAG_SCORE_THRESHOLD 统一过滤。
"""

from functools import lru_cache

from config import settings
from providers.rerank.base import RerankProvider


class NoOpRerank(RerankProvider):
    """空实现 —— 按原顺序返回,分数全 1.0。开发期快速跑通链路用。"""

    name = "none"

    async def rerank(self, query, candidates, top_k=None):
        n = len(candidates) if top_k is None else min(top_k, len(candidates))
        return [(i, 1.0) for i in range(n)]


@lru_cache
def get_reranker() -> RerankProvider:
    provider = settings.rerank.provider
    if provider == "none":
        return NoOpRerank()
    if provider == "local_bge":
        from providers.rerank.local_bge import LocalBGERerank

        return LocalBGERerank()
    if provider == "cross_encoder":
        from providers.rerank.cross_encoder import CrossEncoderRerank

        return CrossEncoderRerank()
    raise ValueError(f"未知 rerank provider: {provider}")
