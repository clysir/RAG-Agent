"""火山方舟 (Volcengine Ark) LLM Provider —— OpenAI 兼容协议。

火山方舟把 Doubao 等模型以 OpenAI 兼容接口暴露,端点:
    https://ark.cn-beijing.volces.com/api/v3

model 字段填**接入点 ID**(endpoint),不是模型本名。从火山方舟控制台获取。
例如:ep-20240xxxxxxx-xxxxx 对应一个具体的模型版本。

API Key 在火山方舟控制台 "API Key 管理" 里生成。
"""

from typing import AsyncIterator

from openai import AsyncOpenAI

from config import settings
from providers.llm.base import LLMProvider, LLMResponse, LLMUsage, Message


class VolcengineLLM(LLMProvider):
    """火山方舟 LLM 实现 —— 复用 OpenAI SDK + Ark 端点。"""

    name = "volcengine"

    def __init__(self) -> None:
        self.model = settings.llm.model
        if not settings.llm.api_key.get_secret_value():
            raise ValueError("LLM_API_KEY 未配置(火山方舟控制台 -> API Key 管理)")
        # base_url 用户没配时默认到火山方舟北京端点
        base_url = settings.llm.base_url or "https://ark.cn-beijing.volces.com/api/v3"
        self._client = AsyncOpenAI(
            api_key=settings.llm.api_key.get_secret_value(),
            base_url=base_url,
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
