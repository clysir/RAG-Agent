"""Web Search Provider —— 联网搜索协议抽象。

为什么要抽象:
- 当前用智谱 web-search-pro,后续可能切博查 / Tavily / Brave Search
- 上层(agent.tools.web_search)只依赖 search(query) -> list[WebResult]
- 切换只改 .env 的 WEB_SEARCH_PROVIDER 字段
"""

from providers.web_search.base import WebResult, WebSearchProvider
from providers.web_search.factory import get_web_search

__all__ = ["WebSearchProvider", "WebResult", "get_web_search"]
