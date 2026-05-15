"""QueryRewriteTool —— QUERY_REWRITE 状态的工具实现。

职责:
1. 调 rag.query_optimizer.optimize_query() 拿到扩展 query 集合(含 rewrite + 可选 HyDE/MultiQuery)
2. 主改写结果写 ctx.rewritten_query(展示/日志)
3. 完整扩展集合写 ctx.expanded_queries(后续 RetrieveTool 跑多路召回)

为什么不直接在 hybrid_search 里做:
- 状态机层面控制 query 扩展,SSE 可向前端透出"我把您的问题理解为 X"
- 避免 RetrieveTool 再调一次 optimize_query 重复工作
"""

from loguru import logger

from agent.context import AgentContext
from agent.tools.base import Tool
from app.core import with_latency
from rag.query_optimizer import optimize_query


class QueryRewriteTool(Tool):
    """改写 query + 扩展多路检索 query。"""

    name = "query_rewrite"

    @with_latency("agent.tool.query_rewrite")
    async def execute(self, ctx: AgentContext) -> dict[str, int]:
        # 把图片理解结果拼到 query 前,补足上下文
        base_query = ctx.user_query
        if ctx.image_description:
            base_query = f"[图片]{ctx.image_description} {base_query}".strip()

        try:
            queries = await optimize_query(base_query, ctx.history or None)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"query_rewrite.fail trace_id={ctx.trace_id} err={e}")
            queries = [base_query]

        # 第一条通常是原始 query,第二条(如果有)是 LLM 改写
        ctx.expanded_queries = queries
        # 主改写 query:取第二条(rewrite 后),没改写就退回原文
        if len(queries) >= 2 and queries[1] != base_query:
            ctx.rewritten_query = queries[1]
        else:
            ctx.rewritten_query = base_query

        logger.info(
            f"query_rewrite.done trace_id={ctx.trace_id} "
            f"main={ctx.rewritten_query!r} expanded={len(queries)}"
        )
        return {"expanded": len(queries)}
