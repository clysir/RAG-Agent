"""OpenAI LLM Provider —— 直接用官方 AsyncOpenAI。

支持任何 OpenAI 兼容端点:OpenAI 官方 / Azure OpenAI / Together / Anyscale / 自部署 vLLM。
切换由 .env 的 LLM_BASE_URL 决定。
"""

from typing import AsyncIterator

from openai import AsyncOpenAI

from config import settings
from providers.llm.base import LLMProvider, LLMResponse, LLMUsage, Message


class OpenAILLM(LLMProvider):
    """OpenAI Chat Completions 实现 —— DeepSeek 也走这套,但 base_url 不同。"""

    name = "openai"

    def __init__(self) -> None:
        self.model = settings.llm.model
        self._client = AsyncOpenAI(
            api_key=settings.llm.api_key.get_secret_value(),
            base_url=settings.llm.base_url or "https://api.openai.com/v1",
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
