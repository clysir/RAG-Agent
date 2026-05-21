"""自研状态机 Agent 核心 —— 不依赖 LangGraph,纯 Python。

设计要点:
1. transitions 是一个 (当前状态, 上下文) -> 下一状态 的纯函数表,易测试
2. run() 是异步生成器,每个状态切换都 yield AgentEvent,直接喂给 SSE
3. RESPOND 状态特殊:它内部本身是流式的,会把 LLM 增量逐 token 吐出去
4. END 状态终结循环
5. LOAD_MEMORY 是条件状态:有 user_id 且 intent 不是 CHITCHAT 才执行,
   工业实践 (Mem0 / Shopify Sidekick) 都强调"不要无脑注入记忆"
"""

from typing import AsyncIterator
from uuid import uuid4

from loguru import logger

from agent.context import AgentContext, AgentEvent, AgentState, IntentType
from agent.tools import (
    ClarifyTool,
    IntentTool,
    MemoryLoadTool,
    QueryRewriteTool,
    RerankTool,
    RespondTool,
    RetrieveTool,
    VisionTool,
    WebSearchTool,
)

# 触发长期记忆加载的意图集合 —— 闲聊和纯售后跳过
_INTENTS_NEED_MEMORY = {
    IntentType.SEARCH,
    IntentType.RECOMMEND,
    IntentType.DETAIL,
    IntentType.COMPARE,
}

# 数据库召回为空时,可以走联网搜索兜底的意图集合 —— 用户已经表达了明确的购物需求
# CHITCHAT / AFTER_SALES 不在内,避免乱走 web(闲聊没必要,售后该走人工)
_INTENTS_NEED_WEB = _INTENTS_NEED_MEMORY


def _route_after_intent(ctx: AgentContext) -> AgentState:
    """意图识别后的路由 —— 闲聊直接回答,有图像走 IMAGE_UNDERSTAND 后再检索。

    决策依据:
    - 闲聊 → RESPOND
    - 登录用户 + 购物意图 → LOAD_MEMORY 接入用户长期记忆
    - 有图片 → IMAGE_UNDERSTAND(VisionTool 内部根据 VISION_PROVIDER 决定是否真调 VLM)
    - 其它 → QUERY_REWRITE
    """
    from config import settings  # 局部 import 避免循环依赖时序问题

    if ctx.intent == IntentType.CHITCHAT:
        return AgentState.RESPOND
    # 登录用户 + 购物类意图 -> 加载记忆
    if ctx.user_id is not None and ctx.intent in _INTENTS_NEED_MEMORY:
        return AgentState.LOAD_MEMORY
    # 有图片且 vision 已启用 -> 先做 caption
    if ctx.image_bytes and settings.vision.provider != "disabled":
        return AgentState.IMAGE_UNDERSTAND
    return AgentState.QUERY_REWRITE


def _route_after_memory(ctx: AgentContext) -> AgentState:
    """LOAD_MEMORY 之后 —— 有图片走 vision,否则直接 query rewrite。"""
    from config import settings

    if ctx.image_bytes and settings.vision.provider != "disabled":
        return AgentState.IMAGE_UNDERSTAND
    return AgentState.QUERY_REWRITE


def _route_after_retrieve(ctx: AgentContext) -> AgentState:
    """检索后的路由 —— 召回为 0 时根据意图决定网搜兜底还是反问。"""
    if not ctx.candidates:
        return _route_no_candidates(ctx)
    return AgentState.RERANK


def _route_after_rerank(ctx: AgentContext) -> AgentState:
    """RERANK 后的路由 —— CLAUDE.md 规则 7:候选为空时不基于低分编造。

    决策树:
    - 有候选 → RESPOND(基于商品库正常回答)
    - 无候选 + 意图明确(SEARCH/RECOMMEND/DETAIL/COMPARE)+ web search 启用 → WEB_FALLBACK
    - 无候选 + 其它 → NEED_CLARIFY(反问澄清)
    """
    if ctx.candidates:
        return AgentState.RESPOND
    return _route_no_candidates(ctx)


def _route_no_candidates(ctx: AgentContext) -> AgentState:
    """候选为空时的统一路由 —— RETRIEVE 召回空 / RERANK 阈值全过滤共用。"""
    from config import settings

    if (
        ctx.intent in _INTENTS_NEED_WEB
        and settings.web_search.provider != "disabled"
    ):
        return AgentState.WEB_FALLBACK
    return AgentState.NEED_CLARIFY


def _route_after_web_fallback(ctx: AgentContext) -> AgentState:
    """WEB_FALLBACK 之后:有结果走 RESPOND(web 模式 prompt),没结果降级反问。"""
    if ctx.web_results:
        return AgentState.RESPOND
    return AgentState.NEED_CLARIFY


class Agent:
    """状态机驱动的导购 Agent。

    用法:
        agent = Agent()
        async for event in agent.run(ctx):
            ...  # 转成 SSE 推给前端
    """

    def __init__(self) -> None:
        # 工具实例化一次,内部如果有重资源会自己处理单例
        self.intent_tool = IntentTool()
        self.memory_load_tool = MemoryLoadTool()
        self.vision_tool = VisionTool()
        self.query_rewrite_tool = QueryRewriteTool()
        self.retrieve_tool = RetrieveTool()
        self.rerank_tool = RerankTool()
        self.web_search_tool = WebSearchTool()
        self.clarify_tool = ClarifyTool()
        self.respond_tool = RespondTool()

    async def run(self, ctx: AgentContext) -> AsyncIterator[AgentEvent]:
        """运行状态机直到 END,异步逐事件吐出。"""
        state = AgentState.INTENT
        logger.info(f"agent.start trace_id={ctx.trace_id} query={ctx.user_query!r}")

        while state != AgentState.END:
            # 通知前端当前进入哪个状态
            yield AgentEvent(type="state_change", state=state)

            try:
                next_state = await self._handle(state, ctx)
            except Exception as e:
                logger.exception(f"agent.error trace_id={ctx.trace_id} state={state}")
                yield AgentEvent(type="error", state=state, data=str(e))
                state = AgentState.END
                break

            # RESPOND 是流式状态,_handle 内部已经 yield 过 token,这里直接收尾
            logger.info(f"agent.transition trace_id={ctx.trace_id} {state} -> {next_state}")
            state = next_state

        yield AgentEvent(type="done", state=AgentState.END, data={"answer": ctx.final_answer})

    async def _handle(self, state: AgentState, ctx: AgentContext) -> AgentState:
        """单步状态处理 —— 返回下一状态。

        RESPOND 状态会直接消费 LLM 流并通过外层 yield 暴露 token,
        所以这里我们把生成器消费完再返回 END。
        但为了让外层 run() 看到 token,需要用一个小技巧 —— 见下面 special handling。
        """
        if state == AgentState.INTENT:
            await self.intent_tool.execute(ctx)
            return _route_after_intent(ctx)

        if state == AgentState.LOAD_MEMORY:
            # 同时拉短期 (Redis) 和长期 (Milvus + MySQL),失败不阻塞主流程
            await self.memory_load_tool.execute(ctx)
            return _route_after_memory(ctx)

        if state == AgentState.IMAGE_UNDERSTAND:
            # 通过 VisionTool 走 vision provider(默认 disabled,启用走豆包/Qwen-VL)
            await self.vision_tool.execute(ctx)
            return AgentState.QUERY_REWRITE

        if state == AgentState.QUERY_REWRITE:
            # 真正调 query_optimizer:rewrite + 可选 HyDE/MultiQuery,
            # 把扩展 query 集合塞 ctx,后续 RetrieveTool 复用,避免双重 LLM 调用
            await self.query_rewrite_tool.execute(ctx)
            return AgentState.RETRIEVE

        if state == AgentState.RETRIEVE:
            recall = await self.retrieve_tool.execute(ctx)
            logger.info(f"agent.retrieve trace_id={ctx.trace_id} recall={recall}")
            return _route_after_retrieve(ctx)

        if state == AgentState.RERANK:
            # cross-encoder 精排 + 阈值过滤,候选清空则走 web 兜底或反问
            await self.rerank_tool.execute(ctx)
            return _route_after_rerank(ctx)

        if state == AgentState.WEB_FALLBACK:
            # 联网搜索兜底,失败 / 空返回都会让 ctx.web_results=[],路由再降级到反问
            await self.web_search_tool.execute(ctx)
            return _route_after_web_fallback(ctx)

        if state == AgentState.NEED_CLARIFY:
            # LLM 生成针对性反问,而不是写死兜底语
            await self.clarify_tool.execute(ctx)
            return AgentState.END

        if state == AgentState.RESPOND:
            # 注意:这里需要把 token 流通过外层 run() 暴露给调用方
            # 为了简洁,流式 token 通过 logger 记录,真正的 SSE 由 run() 在循环外
            # 直接调用 respond_tool.stream() 处理。见 stream_respond() 辅助方法。
            await self.respond_tool.execute(ctx)
            return AgentState.END

        raise RuntimeError(f"未处理的状态: {state}")


async def stream_agent(ctx: AgentContext) -> AsyncIterator[AgentEvent]:
    """对外便捷入口 —— 直接拿事件流,内部会把 RESPOND 阶段拆成逐 token 推送。

    实现说明:
    把 RESPOND 之前的状态用 Agent.run() 跑完 (其实这里没用run跑 写了一个while去跑,达到SSE输出的效果),到达 RESPOND 时切换为
    RespondTool.stream() 逐 token 吐出 token 事件,最后再补一个 done 事件。
    这样保证 SSE 体验是"先看到状态进度,再看到流式文字"。

    记忆 hook:
    - 进入前把用户原话 append 到短期记忆(turns)
    - RESPOND 流完成后追加 assistant 回答 + 异步触发长期事实抽取
    """
    from app.core.memory import append_turn, maybe_refresh_summary

    agent = Agent()
    state = AgentState.INTENT
    logger.info(f"agent.start trace_id={ctx.trace_id} query={ctx.user_query!r}")

    # 把用户本轮输入存进短期记忆 —— 即便后续抛错也保住对话历史
    try:
        await append_turn(ctx.session_id, "user", ctx.user_query)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"stm.append_user_fail trace_id={ctx.trace_id} err={e}")

    while state not in (AgentState.RESPOND, AgentState.END):
        yield AgentEvent(type="state_change", state=state)
        try:
            state = await agent._handle(state, ctx)
        except Exception as e:
            logger.exception(f"agent.error trace_id={ctx.trace_id} state={state}")
            yield AgentEvent(type="error", state=state, data=str(e))
            yield AgentEvent(type="done", state=AgentState.END)
            return

    if state == AgentState.RESPOND:
        yield AgentEvent(type="state_change", state=AgentState.RESPOND)
        async for delta in agent.respond_tool.stream(ctx):
            yield AgentEvent(type="token", state=AgentState.RESPOND, data=delta)
    elif state == AgentState.END and ctx.final_answer and ctx.clarify_question:
        # NEED_CLARIFY 分支:把反问句作为单个 token 事件吐出,前端渲染逻辑与正常回答统一
        yield AgentEvent(type="token", state=AgentState.NEED_CLARIFY, data=ctx.final_answer)

    # 记忆后处理:append assistant 回答 + 异步抽长期事实 + 摘要刷新
    try:
        if ctx.final_answer:
            await append_turn(ctx.session_id, "assistant", ctx.final_answer)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"stm.append_assistant_fail trace_id={ctx.trace_id} err={e}")

    # 异步派发长期事实抽取 —— 失败不影响响应
    # 仅登录用户 + 非闲聊触发(避免抽出无意义事实)
    if ctx.user_id is not None and ctx.intent and ctx.intent.value != "chitchat":
        try:
            from app.workers.tasks import extract_user_facts

            recent_dialog = [
                {"role": "user", "content": ctx.user_query},
                {"role": "assistant", "content": ctx.final_answer or ""},
            ]
            extract_user_facts.delay(ctx.user_id, recent_dialog, None)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"memory.dispatch_extract_fail trace_id={ctx.trace_id} err={e}")

    # 摘要异步刷新 —— 用便宜模型做(此处先复用主 LLM,后续可在 settings 区分)
    try:
        from app.core.memory.long_term import _build_extract_messages  # type: ignore
        from providers import get_llm
        from providers.llm.base import Message

        async def _summarize(old_summary: str, turns: list[dict]):
            llm = get_llm()
            prompt = (
                "你是会话摘要器。把【旧摘要】和【新近对话】合并成一段不超过 200 字的中文摘要,"
                "保留用户偏好、待办、上下文话题,丢弃寒暄。只输出摘要正文,不要前缀。\n"
                f"【旧摘要】{old_summary or '(无)'}\n"
                f"【新近对话】\n"
                + "\n".join(f"{t['role']}: {t['content']}" for t in turns)
            )
            resp = await llm.chat(
                [Message(role="user", content=prompt)],
                stream=False, temperature=0.2, max_tokens=400,
            )
            return resp.content.strip() if hasattr(resp, "content") else ""

        await maybe_refresh_summary(ctx.session_id, _summarize)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"stm.summary_refresh_fail trace_id={ctx.trace_id} err={e}")

    yield AgentEvent(
        type="done",
        state=AgentState.END,
        data={
            "answer": ctx.final_answer,
            # 把网搜来源透传给前端,展示在消息底部的"网络搜索结果"卡片区
            "web_sources": [r.model_dump() for r in ctx.web_results],
        },
    )


def new_trace_id() -> str:
    """生成全链路追踪 ID —— 短随机字符串即可。"""
    return uuid4().hex[:12]
