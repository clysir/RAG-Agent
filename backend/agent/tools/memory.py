"""MemoryLoadTool —— LOAD_MEMORY 状态的工具实现。

职责:
1. 拉短期记忆(Redis):最近 turns、滚动摘要、会话槽位
2. 拉长期记忆(Milvus + MySQL):用户级有效事实,按 query 语义检索 top-k
3. 全部填入 AgentContext 对应字段,供后续 QUERY_REWRITE / RESPOND 消费
4. 任何一路失败都不阻塞主流程 —— 记忆只是辅助,缺了 Agent 仍可工作

为什么独立 Tool 而不直接 inline 状态机:
- 状态机保持纯转移逻辑,IO/LLM 调用统一封装在 Tool
- 便于单测:mock 短期/长期模块即可测 ctx 注入
"""

from loguru import logger

from agent.context import AgentContext
from agent.tools.base import Tool
from app.core import with_latency
from app.core.memory import (
    get_recent_turns,
    get_slots,
    get_summary,
    retrieve_facts,
)


class MemoryLoadTool(Tool):
    """加载短期 + 长期记忆,写入 ctx。"""

    name = "memory_load"

    @with_latency("agent.tool.memory_load")
    async def execute(self, ctx: AgentContext) -> dict[str, int]:
        # 短期:Redis,session 级
        try:
            recent = await get_recent_turns(ctx.session_id)
            summary = await get_summary(ctx.session_id)
            slots = await get_slots(ctx.session_id)
            ctx.history = recent
            ctx.short_term_summary = summary
            ctx.short_term_slots = slots
        except Exception as e:  # noqa: BLE001
            # 记忆系统不可用不应该让对话失败
            logger.warning(f"memory_load.short_term_fail trace_id={ctx.trace_id} err={e}")
            recent = []
            summary = ""
            slots = {}

        # 长期:Milvus + MySQL,user 级,可关闭(LTM_ENABLED=false 时返回空)
        try:
            if ctx.user_id is not None:
                facts = await retrieve_facts(user_id=ctx.user_id, query=ctx.user_query)
                ctx.long_term_facts = [
                    {
                        "fact_id": f.fact_id,
                        "fact_type": f.fact_type,
                        "fact_text": f.fact_text,
                        "score": f.score,
                    }
                    for f in facts
                ]
            else:
                ctx.long_term_facts = []
        except Exception as e:  # noqa: BLE001
            logger.warning(f"memory_load.long_term_fail trace_id={ctx.trace_id} err={e}")
            ctx.long_term_facts = []

        logger.info(
            f"memory_load.done trace_id={ctx.trace_id} "
            f"recent={len(recent)} slots={len(slots)} facts={len(ctx.long_term_facts)} "
            f"has_summary={bool(summary)}"
        )
        return {
            "recent_turns": len(recent),
            "slots": len(slots),
            "facts": len(ctx.long_term_facts),
        }
