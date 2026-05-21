"""最终回答生成工具 —— 流式输出,所以这里直接把生成器交给状态机的 yield。

双模式 prompt:
- 商品模式(默认):有 ctx.candidates 时走原有逻辑
- 网搜模式:WEB_FALLBACK 已填 ctx.web_results 时,切到 web 专用 prompt,
  强制开头"本店没有"+ 引用必须带来源
"""

from typing import AsyncIterator

from agent.context import AgentContext
from agent.prompts.respond import build_products_prompt, build_web_prompt
from agent.tools.base import Tool
from providers import get_llm
from providers.llm import Message


class RespondTool(Tool):
    name = "respond"

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        """流式生成最终回答 —— 调用方用 async for 拿增量文本。"""
        llm = get_llm()
        # 网搜结果非空 → 网搜模式;否则 → 商品模式(原行为)
        if ctx.web_results:
            prompt = build_web_prompt(ctx)
        else:
            prompt = build_products_prompt(ctx)
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
