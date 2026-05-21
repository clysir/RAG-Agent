"""WebSearchTool —— WEB_FALLBACK 状态的工具实现。

职责:
1. 把 image_description + user_query 拼成自然语言 query(去重去冗余)
2. 调 web_search provider(智谱 web-search-pro),失败 / 空返回都视为 0 命中
3. 写入 ctx.web_results,供 RespondTool 切换 prompt 时消费

为什么把失败也写空 list 而不抛:
- 状态机层 _route_after_web_fallback 看 ctx.web_results,空则降级到 NEED_CLARIFY
- 这样 web 抖动 / 限流不会让用户看到 500,而是优雅的"补充信息我帮你查"
"""

from loguru import logger

from agent.context import AgentContext
from agent.tools.base import Tool
from app.core import with_latency
from providers import get_web_search


class WebSearchTool(Tool):
    """联网搜索兜底工具。"""

    name = "web_search"

    @with_latency("agent.tool.web_search")
    async def execute(self, ctx: AgentContext) -> int:
        # provider disabled 直接返回 0,路由会降级到 NEED_CLARIFY
        try:
            ws = get_web_search()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"web_search.init_fail trace_id={ctx.trace_id} err={e}")
            ctx.web_results = []
            return 0
        if ws is None:
            logger.info(f"web_search.disabled trace_id={ctx.trace_id}")
            ctx.web_results = []
            return 0

        query = self._build_query(ctx)
        if not query:
            ctx.web_results = []
            return 0

        results = await ws.search(query)
        ctx.web_results = results
        logger.info(
            f"agent.web_search trace_id={ctx.trace_id} query={query[:60]!r} hits={len(results)}"
        )
        return len(results)

    @staticmethod
    def _build_query(ctx: AgentContext) -> str:
        """拼接检索词 —— 优先用 image_description(具体)+ user_query(意图)。"""
        parts: list[str] = []
        if ctx.image_description:
            parts.append(ctx.image_description.strip())
        # 用户 query 短的话直接拼;长的话只拼后半段(防止重复 caption)
        q = (ctx.user_query or "").strip()
        if q and q not in " ".join(parts):
            parts.append(q)
        return " ".join(parts).strip()
