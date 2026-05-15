"""Query 优化层 —— Rewrite / HyDE / MultiQuery 三种策略,按 .env 开关。

设计:
- 每种策略独立函数,纯粹的 (str, history) -> list[str] 输入输出
- 入口 optimize_query() 编排:逐个看 settings 开关决定是否启用
- 最终输出是一组 query 字符串,后续检索层会对每个 query 独立召回再合并
"""

from loguru import logger

from app.core import with_latency
from config import settings
from providers import get_llm
from providers.llm import Message

# ============ Prompt 模板 ============
_REWRITE_PROMPT = """你是检索 query 改写助手。把下列用户问题改写成更适合电商商品检索的检索式:
- 消除指代/口语化
- 保留关键属性(品类、品牌、价格、风格)
- 输出一句完整 query,不要解释
- 不要把范围词拆成多句

历史上下文:
{history}

用户当前问题:{query}
改写后的 query:"""

_HYDE_PROMPT = """假设你已经检索到一个完美匹配下面问题的商品,请用 1-2 句话写出这个商品的描述
(包含品类、关键参数、风格)。不要写"我推荐",直接像商品文案那样写:

问题:{query}
假设商品描述:"""

_MULTI_QUERY_PROMPT = """把下面用户问题展开成 {n} 个不同角度的检索 query,覆盖:
- 字面意思
- 同义/近义表达
- 上位概念
每行一个 query,不加序号、不加解释。

用户问题:{query}
"""


# ============ 单策略实现 ============


@with_latency("query_opt.rewrite")
async def rewrite_query(query: str, history: list[dict[str, str]] | None = None) -> str:
    """改写 query —— 返回单条改写结果。"""
    history_text = _format_history(history)
    llm = get_llm()
    resp = await llm.chat(
        [Message(role="user", content=_REWRITE_PROMPT.format(history=history_text, query=query))],
        stream=False,
        temperature=0.2,
        max_tokens=120,
    )
    return resp.content.strip() or query  # type: ignore[union-attr]


@with_latency("query_opt.hyde")
async def hyde_query(query: str) -> str:
    """HyDE —— 让 LLM 生成假设性商品描述,后续用其向量去检索。"""
    llm = get_llm()
    resp = await llm.chat(
        [Message(role="user", content=_HYDE_PROMPT.format(query=query))],
        stream=False,
        temperature=0.4,
        max_tokens=150,
    )
    return resp.content.strip() or query  # type: ignore[union-attr]


@with_latency("query_opt.multi_query")
async def multi_query(query: str, n: int | None = None) -> list[str]:
    """MultiQuery —— 把问题展开成 n 个多角度 query。"""
    n = n or settings.query_opt.multi_query_count
    llm = get_llm()
    resp = await llm.chat(
        [Message(role="user", content=_MULTI_QUERY_PROMPT.format(n=n, query=query))],
        stream=False,
        temperature=0.7,
        max_tokens=300,
    )
    lines = [line.strip(" -•\t") for line in resp.content.splitlines() if line.strip()]  # type: ignore[union-attr]
    # 去空、去重,最多取 n 条
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        if line and line not in seen:
            seen.add(line)
            result.append(line)
        if len(result) >= n:
            break
    return result or [query]


# ============ 编排入口 ============


@with_latency("query_opt.optimize")
async def optimize_query(
    query: str, history: list[dict[str, str]] | None = None
) -> list[str]:
    """统一入口 —— 按配置开关返回一组要去检索的 query 集合。

    Returns:
        非空 list,至少包含原始 query。检索层会对每条 query 独立召回再 RRF 融合。
    """
    cfg = settings.query_opt
    queries: list[str] = [query]

    # 改写优先,改完用改写结果继续后续展开
    base_query = query
    if cfg.enable_rewrite:
        try:
            base_query = await rewrite_query(query, history)
            if base_query and base_query != query:
                queries.append(base_query)
        except Exception as e:
            logger.warning(f"query_opt.rewrite_failed reason={e}")

    if cfg.enable_hyde:
        try:
            queries.append(await hyde_query(base_query))
        except Exception as e:
            logger.warning(f"query_opt.hyde_failed reason={e}")

    if cfg.enable_multi_query:
        try:
            queries.extend(await multi_query(base_query))
        except Exception as e:
            logger.warning(f"query_opt.multi_query_failed reason={e}")

    # 去重保序
    seen: set[str] = set()
    deduped: list[str] = []
    for q in queries:
        if q and q not in seen:
            seen.add(q)
            deduped.append(q)
    logger.info(f"query_opt.optimize input={query!r} expanded_count={len(deduped)}")
    return deduped


def _format_history(history: list[dict[str, str]] | None) -> str:
    if not history:
        return "(无)"
    # 只保留最近 4 轮,避免 prompt 过长
    recent = history[-4:]
    return "\n".join(f"{m.get('role', '?')}: {m.get('content', '')}" for m in recent)
