"""检索工具 —— 根据 ctx 是否有图片分流到文本/图像/混合路。

设计:
- 纯文本 → hybrid_search(向量+BM25+RRF+Rerank)
- 带图片 → image_search 加 hybrid_search,各路结果用简单分数加权合并
- 纯图片(query 为空)→ image_search

需要 AsyncSession,所以这里通过依赖注入风格从 ctx 拿:
- 工具不直接持有 session,而是由 chat 接口在调用 stream_agent 时把 session 塞进 ctx.extra
"""

from loguru import logger

from agent.context import AgentContext, ProductCandidate
from agent.tools.base import Tool
from app.core import with_latency
from rag import hybrid_search, image_search


class RetrieveTool(Tool):
    """主检索工具 —— 自动分流图文路径。

    依赖 ctx.extra['session'](AsyncSession) 注入,由 API 层 chat() 设置。
    """

    name = "retrieve"

    @with_latency("agent.tool.retrieve")
    async def execute(self, ctx: AgentContext) -> int:
        session = ctx.extra.get("session") if hasattr(ctx, "extra") else None
        if session is None:
            logger.warning("retrieve.no_session trace_id={}", ctx.trace_id)
            ctx.candidates = []
            return 0

        text_query = ctx.rewritten_query or ctx.user_query
        has_image = bool(ctx.image_bytes)
        has_text = bool(text_query and text_query.strip())

        text_results: list[ProductCandidate] = []
        image_results: list[ProductCandidate] = []

        if has_text:
            text_results = await hybrid_search(text_query, session, history=ctx.history)

        if has_image:
            image_results = await image_search(ctx.image_bytes, session)

        # 合并 —— 简化策略:按 product_id 去重保高分,文本结果优先
        merged: dict[int, ProductCandidate] = {}
        for c in text_results + image_results:
            existing = merged.get(c.product_id)
            if existing is None or c.score > existing.score:
                merged[c.product_id] = c
        # 按分数排序输出
        ctx.candidates = sorted(merged.values(), key=lambda x: x.score, reverse=True)
        logger.info(
            f"agent.retrieve trace_id={ctx.trace_id} "
            f"text_hits={len(text_results)} image_hits={len(image_results)} merged={len(ctx.candidates)}"
        )
        return len(ctx.candidates)
