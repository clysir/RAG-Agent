"""最终回答生成工具 —— 流式输出,所以这里直接把生成器交给状态机的 yield。"""

from typing import AsyncIterator

from agent.context import AgentContext
from agent.tools.base import Tool
from providers import get_llm
from providers.llm import Message

_RESPOND_PROMPT = """你是专业的电商导购助手,基于以下检索到的候选商品,回答用户问题。
要给出:推荐理由、关键参数对比、适合人群、可能的避坑提示。
语气专业、简洁、可信。

候选商品:
{candidates}

用户问题:{query}

请直接给出回答:"""


class RespondTool(Tool):
    name = "respond"

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        """流式生成最终回答 —— 调用方用 async for 拿增量文本。"""
        llm = get_llm()
        candidates_text = self._format_candidates(ctx) or "(暂无召回结果,基于通用知识回答)"
        prompt = _RESPOND_PROMPT.format(candidates=candidates_text, query=ctx.user_query)
        messages = [Message(role="user", content=prompt)]

        stream = await llm.chat(messages, stream=True, temperature=0.5)
        async for delta in stream:  # type: ignore[union-attr]
            ctx.final_answer += delta
            yield delta

    async def execute(self, ctx: AgentContext) -> str:
        # 非流式入口,主要用于测试
        chunks = []
        async for delta in self.stream(ctx):
            chunks.append(delta)
        return "".join(chunks)

    @staticmethod
    def _format_candidates(ctx: AgentContext) -> str:
        # 把候选拼成 prompt 友好的格式,只取前 5 条避免 token 爆炸
        lines = []
        for i, c in enumerate(ctx.candidates[:5], 1):
            price = f"¥{c.price}" if c.price is not None else "价格未知"
            lines.append(f"{i}. {c.title} | {price} | {c.snippet}")
        return "\n".join(lines)
