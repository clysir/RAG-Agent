"""Web Search Provider 协议 + 共享 DTO —— 业务代码只依赖这个接口。

设计要点:
- WebResult 定义在 provider 层(像 rag.types.ProductCandidate),避免 providers 反向 import agent
  (CLAUDE.md 规则 4:依赖方向单向 app → agent → rag/providers → db/config)
- search 失败 / 限流 / 超时一律 return [] + 日志告警,不抛异常 —— 由 Agent 状态机决定是否降级
- query 由调用方拼好(image_description + user_query),Provider 不做改写
"""

from typing import Protocol

from pydantic import BaseModel


class WebResult(BaseModel):
    """单条网络搜索结果 —— Provider 返回的标准化结构。"""

    title: str
    url: str
    snippet: str = ""
    source: str = ""  # 域名,例如 nike.com.cn
    publish_date: str | None = None  # ISO 日期,可选


class WebSearchProvider(Protocol):
    """联网搜索统一接口。"""

    name: str

    async def search(self, query: str, count: int | None = None) -> list[WebResult]:
        """全网搜索 —— 失败返回空列表,不抛异常。

        Args:
            query: 已经拼好的检索词(自然语言)
            count: 返回条数,不传走配置默认值
        """
        ...
