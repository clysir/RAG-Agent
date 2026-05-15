"""RerankTool —— RERANK 状态的工具实现。

职责:
1. 拿 ctx.candidates 作为输入(已经过初步召回 + 第一层 RRF)
2. 用 reranker provider(cross-encoder)以 ctx.user_query 为 query 做精排
3. 应用 score 阈值过滤(防引用噪声),低于阈值直接丢
4. 截断到 settings.rerank.top_k

注意 hybrid_search 内部已经做了一次 rerank。这里是状态机层的二次精排兜底,
未来 RetrieveTool 切到"不做内部 rerank"模式后这里就是唯一的精排位置。
"""

from loguru import logger

from agent.context import AgentContext
from agent.tools.base import Tool
from app.core import with_latency
from config import settings
from providers import get_reranker


class RerankTool(Tool):
    """对候选做 cross-encoder 精排 + 阈值过滤。"""

    name = "rerank"

    @with_latency("agent.tool.rerank")
    async def execute(self, ctx: AgentContext) -> dict[str, int]:
        if not ctx.candidates:
            return {"in": 0, "out": 0}

        reranker = get_reranker()
        # 用 snippet 做 rerank 输入,标题作 fallback —— RAG 的标准做法
        passages = [c.snippet or c.title for c in ctx.candidates]
        ranked = await reranker.rerank(
            ctx.user_query, passages, top_k=settings.rerank.top_k
        )

        # 阈值过滤
        threshold = settings.retrieval.score_threshold
        kept_pairs = [(idx, s) for idx, s in ranked if s >= threshold]

        # 按 rerank 顺序重组,覆盖原 score
        new_candidates = []
        for idx, score in kept_pairs:
            cand = ctx.candidates[idx]
            cand.score = float(score)
            new_candidates.append(cand)

        before = len(ctx.candidates)
        ctx.candidates = new_candidates
        logger.info(
            f"rerank.done trace_id={ctx.trace_id} in={before} out={len(new_candidates)} "
            f"threshold={threshold} top_score={new_candidates[0].score if new_candidates else 0:.3f}"
        )
        return {"in": before, "out": len(new_candidates)}
