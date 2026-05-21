"""RESPOND 状态的 prompt 模板 —— 商品模式 vs 网搜模式双套。

为什么放这里:
- prompts/ 是 agent 模块下专门管 prompt 文本的位置,
  与工具实现解耦,改 prompt 不动代码
- 商品模式 vs 网搜模式 prompt 差异大,必须独立维护避免互相污染
"""

from agent.context import AgentContext
from providers.web_search.base import WebResult
from rag.types import ProductCandidate


PRODUCTS_TEMPLATE = """你是专业的电商导购助手,基于以下检索到的候选商品,回答用户问题。
要给出:推荐理由、关键参数对比、适合人群、可能的避坑提示。
语气专业、简洁、可信。

候选商品:
{candidates}

用户问题:{query}

请直接给出回答:"""


# 网搜模式的 prompt —— 强制声明"本店没有"+ 引用要带来源,杜绝把网搜内容伪装成商品库
WEB_TEMPLATE = """你是专业的电商导购助手。

**重要前提:用户想要的商品在本店商品库里没有匹配**。以下是从联网搜索拿到的外部信息(不是本店商品):

{web_results}

**严格遵守以下规则**:
1. **开头第一句必须说明**:"本店商品库里目前没有这款 / 这类商品,我帮你在网上搜了一下"
2. 引用网络信息时**必须带角标**,格式:[来源:标题 - 域名]
3. **不能假装网搜结果就是本店商品**,不能给出我们能下单购买的暗示
4. 价格、参数等具体数字**只能从网搜结果引用**,拿不到精确数字时说"约""左右",并指明来源
5. 末尾可以建议用户:看看店里有没有同品类的替代品(如果有 ctx 候选)、或去官方旗舰店购买
6. 语气坦诚不浮夸

用户问题:{query}{user_extra}

请直接回答:"""


def build_products_prompt(ctx: AgentContext) -> str:
    """商品库召回成功 —— 走原有逻辑。"""
    cand_text = _format_candidates(ctx.candidates) or "(暂无召回结果,基于通用知识回答)"
    return PRODUCTS_TEMPLATE.format(candidates=cand_text, query=ctx.user_query)


def build_web_prompt(ctx: AgentContext) -> str:
    """网搜兜底 —— 用户问的东西库里没有,但意图明确。"""
    web_text = _format_web_results(ctx.web_results)
    # 用户如果有图,把 VLM 的描述也带上,LLM 才知道用户问的是啥
    user_extra = ""
    if ctx.image_description:
        user_extra = f"\n(用户附图,识别为:{ctx.image_description})"
    return WEB_TEMPLATE.format(
        web_results=web_text,
        query=ctx.user_query,
        user_extra=user_extra,
    )


def _format_candidates(candidates: list[ProductCandidate]) -> str:
    """商品候选 → prompt 友好的列表,只取前 5 条避免 token 爆炸。"""
    lines = []
    for i, c in enumerate(candidates[:5], 1):
        price = f"¥{c.price}" if c.price is not None else "价格未知"
        lines.append(f"{i}. {c.title} | {price} | {c.snippet}")
    return "\n".join(lines)


def _format_web_results(results: list[WebResult]) -> str:
    """网搜结果 → prompt 友好的列表。"""
    if not results:
        return "(无搜索结果)"
    lines = []
    for i, r in enumerate(results, 1):
        date = f" · {r.publish_date}" if r.publish_date else ""
        lines.append(
            f"[{i}] {r.title}{date}\n"
            f"     来源: {r.source or r.url}\n"
            f"     摘要: {r.snippet}"
        )
    return "\n\n".join(lines)
