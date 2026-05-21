"""智谱 web-search-pro 实现 —— 复用智谱开放平台 API Key,不需要单独注册。

接入方式:
- 智谱平台提供 "Web Search API",作为 tools 工具传给 chat.completions
  endpoint:POST https://open.bigmodel.cn/api/paas/v4/web_search
  这是独立端点,不走 chat 模型,响应里直接给搜索结果

参考:
- https://docs.bigmodel.cn/cn/guide/tools/web-search
- https://open.bigmodel.cn/dev/api/search-tool/web-search-pro

请求体:
    {
        "search_engine": "search_pro",
        "search_query": "Nike 跑鞋 ZoomX 价格",
        "count": 5,
        "search_recency_filter": "noLimit",
        "request_id": "<uuid>"
    }

响应:
    {
        "id": "...",
        "search_intent": [...],
        "search_result": [
            {"link":"https://...", "title":"...", "content":"...", "media":"...", "publish_date":"..."},
            ...
        ]
    }
"""

import uuid
from urllib.parse import urlparse

import httpx
from loguru import logger

from app.core import with_latency
from config import settings
from providers.web_search.base import WebResult, WebSearchProvider


class ZhipuWebSearch(WebSearchProvider):
    """智谱开放平台 web-search-pro 工具。"""

    name = "zhipu_web_search"

    def __init__(self) -> None:
        cfg = settings.web_search
        key = cfg.api_key.get_secret_value()
        if not key:
            raise ValueError("WEB_SEARCH_API_KEY 未配置 —— 智谱平台 API Key,可复用 VISION_API_KEY")
        self._api_key = key
        self._engine = cfg.engine
        self._count = cfg.count
        self._recency = cfg.recency
        self._timeout = cfg.timeout
        # 智谱 web search 走独立端点,不是 chat.completions
        self._endpoint = f"{cfg.base_url.rstrip('/')}/web_search"

    @with_latency("web_search.zhipu")
    async def search(self, query: str, count: int | None = None) -> list[WebResult]:
        if not query.strip():
            return []
        payload = {
            "search_engine": self._engine,
            "search_query": query.strip()[:512],  # 智谱限长
            "count": count or self._count,
            "search_recency_filter": self._recency,
            "request_id": uuid.uuid4().hex,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(self._endpoint, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            logger.warning(f"web_search.http_fail provider=zhipu err={e}")
            return []
        except Exception as e:  # noqa: BLE001
            logger.warning(f"web_search.unexpected_fail provider=zhipu err={e}")
            return []

        raw_results = data.get("search_result") or []
        out: list[WebResult] = []
        for r in raw_results:
            url = (r.get("link") or "").strip()
            title = (r.get("title") or "").strip()
            if not url or not title:
                continue
            out.append(
                WebResult(
                    title=title,
                    url=url,
                    snippet=(r.get("content") or "").strip()[:500],
                    source=_domain_of(url),
                    publish_date=(r.get("publish_date") or None),
                )
            )
        logger.info(
            f"web_search.done provider=zhipu engine={self._engine} "
            f"query={query[:60]!r} hits={len(out)}"
        )
        return out


def _domain_of(url: str) -> str:
    """从 URL 提取一级域名(去掉 www.)。失败返回空串。"""
    try:
        netloc = urlparse(url).netloc
        return netloc.removeprefix("www.")
    except Exception:  # noqa: BLE001
        return ""
