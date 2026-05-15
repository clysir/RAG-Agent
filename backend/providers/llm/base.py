"""LLM Provider 协议 —— 业务代码只依赖这个接口,不关心具体 SDK。"""

from typing import AsyncIterator, Literal, Protocol

from pydantic import BaseModel


class Message(BaseModel):
    """对话消息 —— OpenAI 风格,所有 provider 必须支持这种格式。"""

    role: Literal["system", "user", "assistant", "tool"]
    content: str


class LLMUsage(BaseModel):
    """Token 使用量 —— 用于日志和成本统计。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMResponse(BaseModel):
    """非流式响应封装。"""

    content: str
    usage: LLMUsage | None = None
    model: str


class LLMProvider(Protocol):
    """所有 LLM provider 必须实现的接口。

    设计原则:
    - chat() 一份接口同时支持流式和非流式,由 stream 参数切换
    - 流式返回 AsyncIterator[str],每个 chunk 是增量文本(delta)
    - 非流式返回完整 LLMResponse
    """

    name: str
    model: str

    async def chat(
        self,
        messages: list[Message],
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> LLMResponse | AsyncIterator[str]:
        ...
