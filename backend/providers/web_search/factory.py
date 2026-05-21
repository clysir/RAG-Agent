"""Web Search Provider 工厂 —— 按 settings.web_search.provider 实例化。"""

from functools import lru_cache

from config import settings
from providers.web_search.base import WebSearchProvider


@lru_cache
def get_web_search() -> WebSearchProvider | None:
    """根据配置返回 provider 实例;disabled 返回 None,调用方需自行判空。"""
    provider = settings.web_search.provider
    if provider == "disabled":
        return None
    if provider == "zhipu":
        from providers.web_search.zhipu import ZhipuWebSearch

        return ZhipuWebSearch()
    raise ValueError(f"未知 WEB_SEARCH_PROVIDER: {provider}")
