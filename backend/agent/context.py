"""Agent 上下文与事件类型 —— 状态机运行期间的所有数据载体。"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

# 跨层 DTO:商品候选住在 rag.types、网搜结果住在 providers.web_search.base
# 都是底层模块自己的产物,这里只 re-export 给 agent 内部用,避免 providers/rag 反向 import agent
from rag.types import ProductCandidate
from providers.web_search.base import WebResult


class AgentState(str, Enum):
    """Agent 状态机的所有状态。

    流程: INTENT → (LOAD_MEMORY) → (IMAGE_UNDERSTAND) → QUERY_REWRITE → RETRIEVE
          → RERANK → (NEED_CLARIFY | WEB_FALLBACK) → RESPOND → END
    括号内的状态根据上下文条件触发。

    WEB_FALLBACK:RERANK 后 candidates 为空、但意图明确(SEARCH/RECOMMEND/DETAIL/COMPARE)
                  且信息充分时触发。联网搜索拿外部信息兜底,Respond 用专用 prompt
                  明确告知"本店没有,以下是网上信息",避免把网搜结果伪装成商品库内容。
                  失败 / 返回空 → 降级到 NEED_CLARIFY。
    """

    INTENT = "intent"  # 意图识别
    LOAD_MEMORY = "load_memory"  # 加载短期 + 长期记忆(条件触发)
    IMAGE_UNDERSTAND = "image_understand"  # 图片理解(仅当用户上传图片)
    QUERY_REWRITE = "query_rewrite"  # 检索 query 改写
    RETRIEVE = "retrieve"  # RAG 检索商品库
    RERANK = "rerank"  # 候选精排
    WEB_FALLBACK = "web_fallback"  # 库里没有但意图明确 → 联网兜底
    NEED_CLARIFY = "need_clarify"  # 信息不足,反问用户
    RESPOND = "respond"  # 生成最终回复
    END = "end"  # 流程结束


class IntentType(str, Enum):
    """意图分类 —— 影响后续工具调用路径。"""

    SEARCH = "search"  # 找商品
    COMPARE = "compare"  # 对比商品
    DETAIL = "detail"  # 问参数详情
    RECOMMEND = "recommend"  # 求推荐/搭配
    AFTER_SALES = "after_sales"  # 售后
    CHITCHAT = "chitchat"  # 闲聊


class AgentContext(BaseModel):
    """单次 Agent 运行的全局上下文 —— 所有 Tool 都读写这个对象。

    设计要点:
    - 用 Pydantic BaseModel 保证类型安全和序列化能力
    - history 是多轮上下文,从 Redis 会话状态加载
    - 各状态产出的中间结果都挂在这里,避免参数透传地狱
    - 记忆字段在 LOAD_MEMORY 状态填充,后续 QUERY_REWRITE / RESPOND 消费
    """

    trace_id: str  # 全链路追踪 ID
    session_id: str  # 会话 ID,用于读写 Redis 短期记忆
    user_id: int | None = None  # 登录用户 ID;匿名访问时 None,长期记忆相关功能被跳过
    user_query: str  # 本轮用户原始输入
    image_bytes: bytes | None = None  # 用户上传的图片(可选)

    # 各状态产出
    intent: IntentType | None = None
    image_description: str | None = None  # 图片理解的文字描述
    rewritten_query: str | None = None  # 主改写 query(消解口语/指代后,用于展示)
    # 扩展 query 集合 —— 含 rewrite + HyDE + MultiQuery,RetrieveTool 用此跑多路召回
    expanded_queries: list[str] = Field(default_factory=list)
    candidates: list[ProductCandidate] = Field(default_factory=list)
    # WEB_FALLBACK 状态填充的联网搜索结果。非空时 RespondTool 切到 web 专用 prompt。
    web_results: list[WebResult] = Field(default_factory=list)
    clarify_question: str | None = None  # 需要反问用户时的问题
    final_answer: str = ""  # 最终回复(流式时为累积值)

    # ============ 记忆(LOAD_MEMORY 状态填充) ============
    # 短期:Redis 拉来的最近原文 + 滚动摘要 + 会话槽位
    short_term_summary: str = ""
    short_term_slots: dict[str, Any] = Field(default_factory=dict)
    # 长期:Milvus 命中的用户事实(已过阈值 + 仅 valid_to=NULL)
    long_term_facts: list[dict[str, Any]] = Field(default_factory=list)

    # 多轮历史 —— 由会话存储加载(短期 turns 的原文)
    history: list[dict[str, str]] = Field(default_factory=list)

    # 运行时依赖注入袋 —— 比如 AsyncSession、当前用户上下文等不便序列化的对象
    # 不会被 model_dump 暴露给前端
    extra: dict[str, Any] = Field(default_factory=dict, exclude=True)

    model_config = {"arbitrary_types_allowed": True}


class AgentEvent(BaseModel):
    """状态机对外吐出的事件 —— 直接喂给 SSE。

    前端根据 type 渲染不同 UI:
    - state_change: 显示"正在识别意图..."这类进度
    - tool_output: 显示中间结果(候选商品卡片预览)
    - token: LLM 流式增量文本
    - error: 错误提示
    - done: 标记本轮结束
    """

    type: Literal["state_change", "tool_output", "token", "error", "done"]
    state: AgentState | None = None
    data: Any = None
