"""意图识别工具 —— 用 LLM 把用户输入分类到 IntentType。

实现策略:
- 用 few-shot prompt 让 LLM 直接输出类别字符串
- 失败时 fallback 到 SEARCH(电商场景最常见的意图)
"""

from agent.context import AgentContext, IntentType
from agent.tools.base import Tool
from providers import get_llm
from providers.llm import Message

# Prompt 在这里写死是为了演示,后续会迁到 agent/prompts/intent.txt
_INTENT_PROMPT = """你是电商导购 Agent 的意图分类器。请把用户输入归到以下类别之一,只输出类别名,不要解释:
- search:找商品
- compare:对比商品
- detail:问商品参数详情
- recommend:求推荐或搭配
- after_sales:售后问题
- chitchat:闲聊或无关

用户输入:{query}
类别:"""


class IntentTool(Tool):
    name = "intent"

    async def execute(self, ctx: AgentContext) -> IntentType:
        llm = get_llm()
        messages = [Message(role="user", content=_INTENT_PROMPT.format(query=ctx.user_query))]
        resp = await llm.chat(messages, stream=False, temperature=0.0, max_tokens=20)
        # resp 是 LLMResponse(非流式)
        raw = resp.content.strip().lower() if hasattr(resp, "content") else ""

        # 容错:LLM 可能多输出标点,只取前缀匹配
        for it in IntentType:
            if raw.startswith(it.value):
                ctx.intent = it
                return it
        # 兜底 —— 电商场景默认认为是找商品
        ctx.intent = IntentType.SEARCH
        return IntentType.SEARCH
