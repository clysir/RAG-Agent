"""视觉 Provider 工厂 —— 按 settings.vision.provider 选实现。"""

from functools import lru_cache

from config import settings
from providers.vision.base import VisionProvider


@lru_cache
def get_vision() -> VisionProvider:
    """视觉 provider 单例 —— disabled 时返回空实现保证状态机不挂。"""
    provider = settings.vision.provider
    if provider == "disabled":
        from providers.vision.disabled import DisabledVision

        return DisabledVision()
    if provider == "volcengine":
        from providers.vision.volcengine import VolcengineVision

        return VolcengineVision()
    if provider == "openai":
        from providers.vision.openai import OpenAIVision

        return OpenAIVision()
    raise ValueError(f"未知 vision provider: {provider}")
