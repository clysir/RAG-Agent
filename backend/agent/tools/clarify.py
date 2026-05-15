"""ClarifyTool —— NEED_CLARIFY 状态的工具实现。

职责:
1. 检查 ctx 中已知槽位(short_term_slots + long_term_facts)
2. 列出可能缺失的维度(类目/品牌/预算/尺码/场景)
3. 用 LLM 生成 1 句简短中文反问,写入 ctx.clarify_question 和 ctx.final_answer

设计依据:
- Shopify Sidekick 工程经验:反问要具体、单一,不要给用户"请补充更多信息"这种空话
- 用 LLM 而非模板,因为电商场景下"还需要什么信息"高度依赖原 query 语义
"""

from loguru import logger

from agent.context import AgentContext
from agent.tools.base import Tool
from app.core import with_latency
from providers import get_llm
from providers.llm.base import Message

_CLARIFY_PROMPT_TEMPLATE = """你是电商导购助手。用户问题:
{query}

【已知信息】
{known}

【缺失维度提示】
{missing_hint}

任务:基于上述信息,生成**一句**简短中文反问(20 字以内),帮助你后续给出更精准的推荐。
要求:
- 只问最关键的一个维度,不要罗列
- 不要用"请问"开头,直接问
- 不要重复用户原话
- 不要承诺还会再问

只输出反问句,不要解释。"""

# 电商导购常见的"缺失维度"参考清单 —— 让 LLM 知道有哪些可问
_COMMON_DIMENSIONS = "品类 / 预算价位 / 风格偏好 / 使用场合 / 尺码 / 颜色 / 品牌"


def _build_known_block(ctx: AgentContext) -> tuple[str, str]:
    """汇总已知信息和已问过的维度,返回 (known_text, missing_hint)。"""
    known_parts: list[str] = []
    if ctx.short_term_slots:
        for k, v in ctx.short_term_slots.items():
            known_parts.append(f"- 槽位 {k}: {v}")
    if ctx.long_term_facts:
        for f in ctx.long_term_facts[:5]:
            known_parts.append(f"- 用户事实({f.get('fact_type')}): {f.get('fact_text')}")
    known_text = "\n".join(known_parts) if known_parts else "(无)"

    # 简单启发:已知维度从清单里剔除,剩下的就是候选缺失维度
    known_keys = set()
    for k in (ctx.short_term_slots or {}).keys():
        known_keys.add(k)
    for f in ctx.long_term_facts:
        known_keys.add(f.get("fact_type", ""))

    dims = [d.strip() for d in _COMMON_DIMENSIONS.split("/")]
    missing = [d for d in dims if not any(k in d or d in k for k in known_keys)]
    missing_hint = " / ".join(missing) or _COMMON_DIMENSIONS
    return known_text, missing_hint


class ClarifyTool(Tool):
    """LLM 生成针对性反问。"""

    name = "clarify"

    @with_latency("agent.tool.clarify")
    async def execute(self, ctx: AgentContext) -> str:
        known, missing_hint = _build_known_block(ctx)
        prompt = _CLARIFY_PROMPT_TEMPLATE.format(
            query=ctx.user_query, known=known, missing_hint=missing_hint
        )

        try:
            llm = get_llm()
            resp = await llm.chat(
                [Message(role="user", content=prompt)],
                stream=False,
                temperature=0.4,
                max_tokens=80,
            )
            text = resp.content.strip() if hasattr(resp, "content") else ""
        except Exception as e:  # noqa: BLE001
            logger.warning(f"clarify.llm_fail trace_id={ctx.trace_id} err={e}")
            text = ""

        # 兜底:LLM 失败时按缺失维度给固定提示,起码比"请补充更多信息"具体
        if not text:
            first_missing = missing_hint.split(" / ")[0] if missing_hint else "更多信息"
            text = f"方便告诉我您的{first_missing}吗?"

        ctx.clarify_question = text
        ctx.final_answer = text
        logger.info(f"clarify.done trace_id={ctx.trace_id} question={text!r}")
        return text
