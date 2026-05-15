# agent/ —— 自研状态机 Agent

> 不引入 LangGraph / LangChain Agent,纯 Python 状态机,所有状态转移可单测。

依赖方向:`agent → rag / providers / db / config`,可以被 `app` 调用。

---

## 📂 文件

```
agent/
├── context.py          # AgentContext + AgentState 枚举 + AgentEvent + IntentType
├── state_machine.py    # Agent 类 + stream_agent 入口 + 路由函数
├── base.py             # 工具基类(Protocol)
├── tools/              # 8 个工具,每个对应一个状态
└── prompts/            # prompt 模板(.txt / .jinja)
```

---

## 🗺️ 状态机

```
       ┌─────────────────────────────────────────────────────────────┐
       │                                                             │
       ▼                                                             │
   ┌────────┐  CHITCHAT                                              │
   │ INTENT │─────────────────────────────────────────────► RESPOND─┤
   └───┬────┘                                                        │
       │                                                             │
       │ 登录 + 购物意图                                              │
       ├───────────► LOAD_MEMORY ──┐                                 │
       │                            │                                │
       │ 其它                       │                                │
       └────────────────────────────┤                                │
                                    ▼                                │
                          带图 + vision 启用                          │
                    ┌──────────► IMAGE_UNDERSTAND ──┐                │
                    │                                │                │
                    │ 无图 / vision 关                │                │
                    └────────────────────────────────┤                │
                                                     ▼                │
                                              QUERY_REWRITE           │
                                                     │                │
                                                     ▼                │
                                                 RETRIEVE             │
                                                     │                │
                                       召回 = 0  ┌──┴──┐ 召回 > 0     │
                                                 ▼     ▼              │
                                          NEED_CLARIFY  RERANK        │
                                                 │       │            │
                                                 │  全部 < 阈值        │
                                                 │       ├─► NEED_CLARIFY
                                                 │       │            │
                                                 │  有命中             │
                                                 │       └────► RESPOND
                                                 ▼                    │
                                                END                   │
```

**状态转移函数**(`state_machine.py`):
- `_route_after_intent(ctx)`:看意图类型 + 是否登录 + 是否有图,纯函数
- `_route_after_memory(ctx)`:有图走 vision,否则 query rewrite
- `_route_after_retrieve(ctx)`:召回为空走 NEED_CLARIFY

所有路由函数都不写状态机,只看 ctx,易测。

---

## 🧰 工具(`agent/tools/`)

| 工具 | 状态 | 实现要点 |
|------|------|---------|
| `IntentTool` | INTENT | LLM 分类:SEARCH/RECOMMEND/DETAIL/COMPARE/CHITCHAT/FAQ;附带槽位抽取 |
| `MemoryLoadTool` | LOAD_MEMORY | 拉 Redis 短期窗口 + Milvus 长期事实(`top_k=5`, `score>=0.35`),写 ctx |
| `VisionTool` | IMAGE_UNDERSTAND | 走 `vision provider`(默认 disabled);启用时 base64 转 data URL 喂豆包/GPT-4o |
| `QueryRewriteTool` | QUERY_REWRITE | 调 `rag/query_optimizer/optimize_query`,产出 `ctx.rewritten_query` + `ctx.expanded_queries` |
| `RetrieveTool` | RETRIEVE | `rag/retrievers/hybrid_search`:Dense + Sparse + RRF,top-30 候选 |
| `RerankTool` | RERANK | cross-encoder 精排 + 阈值过滤(`RAG_SCORE_THRESHOLD`),空则路由到 NEED_CLARIFY |
| `ClarifyTool` | NEED_CLARIFY | LLM 生 1 句简短反问(≤20 字),写 `ctx.clarify_question` + `ctx.final_answer` |
| `RespondTool` | RESPOND | 流式 LLM,带引用回答;**模板要求 LLM 只能基于 candidates 编排,不准编造** |

工具基类:`Tool(Protocol)` 只要求一个 `async execute(ctx) -> Any`。

---

## 📦 AgentContext(`context.py`)

每次 `/chat` 创建一个,贯穿状态机:

```python
@dataclass
class AgentContext:
    trace_id: str
    session_id: str
    user_query: str
    user_id: int | None              # None=游客,影响 LOAD_MEMORY 路由
    image_bytes: bytes | None        # 上传的图片二进制
    intent: IntentType | None
    image_caption: str | None        # VLM 输出
    rewritten_query: str | None      # query rewrite 结果
    expanded_queries: list[str]      # HyDE / MultiQuery 展开
    short_term_summary: str          # Redis 拉的摘要
    short_term_slots: dict           # 已知槽位
    long_term_facts: list[dict]      # Milvus 召回的事实
    candidates: list[ProductCandidate]   # 召回 + 精排结果
    clarify_question: str | None
    final_answer: str | None
    extra: dict                      # 运行时杂物:DB session, user 对象
```

注意:`ProductCandidate` 定义在 `rag/types.py`,**不在** `agent/context.py`,避免 rag→agent 反向 import。

---

## 🎬 入口:`stream_agent(ctx)`

```python
async def stream_agent(ctx: AgentContext) -> AsyncIterator[AgentEvent]:
    # 1. 进入前 hook:写短期记忆 user turn
    await append_turn(ctx.session_id, "user", ctx.user_query)

    # 2. 跑状态机直到 RESPOND 或 END
    while state not in (RESPOND, END):
        yield state_change_event
        state = await agent._handle(state, ctx)

    # 3. RESPOND 状态:流式 LLM 逐 token 吐
    if state == RESPOND:
        async for delta in respond_tool.stream(ctx):
            yield token_event(delta)

    # 4. NEED_CLARIFY → END:把反问句作为单 token 事件吐出(前端渲染逻辑统一)
    elif state == END and ctx.final_answer and ctx.clarify_question:
        yield token_event(ctx.final_answer)

    # 5. 收尾 hook:
    #   - 写短期记忆 assistant turn
    #   - 派发 Celery 异步抽长期事实(仅登录用户 + 非闲聊)
    #   - 触发摘要刷新(token 超阈值时 LLM 重压缩)
    yield done_event
```

异步任务**绝不阻塞响应**,失败仅打 warning 不向上抛。

---

## 🧪 单测建议

- 路由函数(`_route_after_*`):喂构造的 `ctx`,断言返回的 state
- 每个工具:Provider mock 掉,断言 ctx 字段被正确填充
- 端到端:用 `scripts/eval.py` 跑 `tests/eval_queries.jsonl`,看 Recall@K
