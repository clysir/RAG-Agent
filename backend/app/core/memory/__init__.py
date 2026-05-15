"""Agent 记忆模块 —— 短期 (Redis) + 长期 (MySQL + Milvus) 混合架构。

依据 CLAUDE.md 附录的工业调研 (Mem0 / MemGPT / Zep):
- 短期记忆:对话级 Redis,滑动窗口 + 滚动摘要,token 阈值触发
- 长期记忆:用户级,LLM 异步抽取离散事实,BGE-M3 嵌入存 Milvus,user_id partition 硬隔离
- 状态机条件检索:仅 intent ∈ {recommend, search} 时加载长期记忆,避免 prompt 膨胀
"""

from app.core.memory.long_term import (
    FactExtractionResult,
    FactOp,
    RetrievedFact,
    apply_facts,
    extract_facts,
    forget_all,
    forget_fact,
    retrieve_facts,
)
from app.core.memory.short_term import (
    SHORT_TERM_TURN_LIMIT,
    append_turn,
    clear_session,
    get_recent_turns,
    get_slots,
    get_summary,
    maybe_refresh_summary,
    set_slot,
)

__all__ = [
    # 短期
    "SHORT_TERM_TURN_LIMIT",
    "append_turn",
    "clear_session",
    "get_recent_turns",
    "get_slots",
    "get_summary",
    "maybe_refresh_summary",
    "set_slot",
    # 长期
    "FactExtractionResult",
    "FactOp",
    "RetrievedFact",
    "apply_facts",
    "extract_facts",
    "forget_all",
    "forget_fact",
    "retrieve_facts",
]
