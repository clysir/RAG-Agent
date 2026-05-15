"""DeepSeek LLM Provider —— 兼容 OpenAI SDK,直接复用 openai 库的 AsyncClient。"""

from typing import AsyncIterator

from openai import AsyncOpenAI

from config import settings
from providers.llm.base import LLMProvider, LLMResponse, LLMUsage, Message


class DeepSeekLLM(LLMProvider):
    """DeepSeek 实现 —— 使用 OpenAI 兼容协议,通过 base_url 切到 deepseek.com。"""

    name = "deepseek"

    def __init__(self) -> None:
        self.model = settings.llm.model
        # DeepSeek API 完全兼容 OpenAI 协议,直接用官方 SDK
        self._client = AsyncOpenAI(
            api_key=settings.llm.api_key.get_secret_value(),
            base_url=settings.llm.base_url,
            timeout=settings.llm.timeout,
        )

    async def chat(
        self,
        messages: list[Message],
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> LLMResponse | AsyncIterator[str]:
        # 把内部 Message 模型转成 OpenAI SDK 期望的 dict
        payload = [m.model_dump() for m in messages]

        if stream:
            return self._stream(payload, temperature, max_tokens, **kwargs)

        resp = await self._client.chat.completions.create(
            model=self.model,
            messages=payload,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
            **kwargs,
        )
        usage = resp.usage
        return LLMResponse(
            content=resp.choices[0].message.content or "",
            usage=LLMUsage(
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
            ),
            model=self.model,
        )

    async def _stream(
        self, payload, temperature, max_tokens, **kwargs
    ) -> AsyncIterator[str]:
        """内部流式生成器 —— 只 yield 增量文本片段。"""
        stream = await self._client.chat.completions.create(
            model=self.model,
            messages=payload,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
