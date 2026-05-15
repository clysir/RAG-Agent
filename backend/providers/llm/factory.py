"""LLM 工厂 —— 根据 settings.llm.provider 选择具体实现。

业务代码用法:
    from providers import get_llm
    llm = get_llm()
    resp = await llm.chat(messages)
"""

from functools import lru_cache

from config import settings
from providers.llm.base import LLMProvider


@lru_cache
def get_llm() -> LLMProvider:
    """返回当前配置的 LLM 实例 —— 进程内单例,避免重复建客户端。"""
    provider = settings.llm.provider

    if provider == "deepseek":
        from providers.llm.deepseek import DeepSeekLLM

        return DeepSeekLLM()

    if provider == "volcengine":
        from providers.llm.volcengine import VolcengineLLM

        return VolcengineLLM()

    if provider == "openai":
        from providers.llm.openai import OpenAILLM

        return OpenAILLM()

    raise ValueError(f"未知 LLM provider: {provider}")
