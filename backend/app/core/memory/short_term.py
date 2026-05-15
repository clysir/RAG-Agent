"""短期记忆 —— 会话级 Redis,滑动窗口 + 滚动摘要 + 槽位状态。

数据结构 (Redis):
  mem:stm:{sid}:turns      List<JSON>   原文消息列表,append 进,FIFO 截断
  mem:stm:{sid}:summary    String       超过 token 阈值后,LLM 生成的滚动摘要
  mem:stm:{sid}:slots      Hash         本轮已抽取的槽位(intent / budget / size / occasion)
  mem:stm:{sid}:turn_count String       总轮数计数,decay 用

设计依据 (CLAUDE.md 调研):
- 工业共识:token-based 截断 > turn-based(多模态轮长不均) — Mem0 摘要指南
- 滑动窗口 + 滚动摘要混合是默认套路 — LangChain ConversationSummaryBufferMemory
- 摘要 break-even 约 27 轮以内,以下做摘要是净开销 — Mem0 实验
- 摘要走便宜模型节省成本(我们 LLM provider 已抽象,切换 .env 即可)

不在这里做:
- 长期事实抽取(走 Celery 异步,长期模块负责)
- 跨会话用户偏好(那是长期记忆职责)
"""

import json
import time
from typing import Any

from loguru import logger

from app.core.redis_client import get_redis
from config import settings

# Redis key 前缀,统一命名避免与其他 Redis 用途冲突
_PREFIX = "mem:stm"


def _k_turns(sid: str) -> str:
    return f"{_PREFIX}:{sid}:turns"


def _k_summary(sid: str) -> str:
    return f"{_PREFIX}:{sid}:summary"


def _k_slots(sid: str) -> str:
    return f"{_PREFIX}:{sid}:slots"


def _k_turn_count(sid: str) -> str:
    return f"{_PREFIX}:{sid}:turn_count"


# 内存里保留的原文轮数硬上限 —— 即便 token 阈值没触发,也不让 list 无限增长
# (用户极短消息 100 条也才几百 token,但 Redis list 操作会变慢)
SHORT_TERM_TURN_LIMIT = max(settings.memory.stm_recent_turns * 4, 32)


def _estimate_tokens(text: str) -> int:
    """粗略估 token 数 —— 中文按字符算,1.5x 经验系数,够触发摘要决策即可。

    生产可换 tiktoken / sentence-transformers tokenizer 精确算,
    这里要求 O(1) 且不引依赖。
    """
    # 中文每字 ~1 token,英文 ~0.25,折中按 0.7 处理
    return int(len(text) * 0.7)


async def append_turn(session_id: str, role: str, content: str) -> None:
    """追加一条对话 —— role: user / assistant / system,content: 文本。

    超出硬上限时 LTRIM 截断老消息(摘要负责承接老消息的信息)。
    """
    if not content:
        return
    r = get_redis()
    payload = json.dumps({"role": role, "content": content, "ts": int(time.time())}, ensure_ascii=False)
    pipe = r.pipeline()
    pipe.rpush(_k_turns(session_id), payload)
    pipe.ltrim(_k_turns(session_id), -SHORT_TERM_TURN_LIMIT, -1)
    pipe.incr(_k_turn_count(session_id))
    pipe.expire(_k_turns(session_id), settings.memory.stm_ttl_seconds)
    pipe.expire(_k_turn_count(session_id), settings.memory.stm_ttl_seconds)
    await pipe.execute()


async def get_recent_turns(session_id: str, n: int | None = None) -> list[dict[str, Any]]:
    """取最近 N 轮原文 —— n 不传则用 settings.memory.stm_recent_turns。"""
    n = n or settings.memory.stm_recent_turns
    r = get_redis()
    raw = await r.lrange(_k_turns(session_id), -n, -1)
    out: list[dict[str, Any]] = []
    for item in raw:
        try:
            out.append(json.loads(item))
        except json.JSONDecodeError:
            logger.warning(f"stm.bad_json sid={session_id} raw={item[:80]}")
    return out


async def get_summary(session_id: str) -> str:
    """取滚动摘要 —— 没生成过返回空串。"""
    r = get_redis()
    s = await r.get(_k_summary(session_id))
    return s or ""


async def maybe_refresh_summary(
    session_id: str,
    summarize_fn: Any,
) -> bool:
    """检查当前轮数是否超过阈值,超过则重新生成摘要。

    Args:
        session_id: 会话 ID
        summarize_fn: 异步函数 (old_summary, turns_to_compress) -> new_summary
                      传入 LLM 抽象;调用方决定用哪个模型(廉价模型即可)

    Returns:
        是否真的重新摘要了
    """
    r = get_redis()
    all_turns_raw = await r.lrange(_k_turns(session_id), 0, -1)
    if not all_turns_raw:
        return False

    # 累加 token 估算,粗暴但足够
    total_tokens = sum(_estimate_tokens(item) for item in all_turns_raw)
    if total_tokens < settings.memory.stm_token_threshold:
        return False

    # 拆分:最近 recent_turns 轮保留原文,前面的进摘要
    recent_n = settings.memory.stm_recent_turns
    if len(all_turns_raw) <= recent_n:
        return False

    to_compress_raw = all_turns_raw[:-recent_n]
    keep_raw = all_turns_raw[-recent_n:]

    to_compress: list[dict[str, Any]] = []
    for item in to_compress_raw:
        try:
            to_compress.append(json.loads(item))
        except json.JSONDecodeError:
            continue

    old_summary = await get_summary(session_id)
    new_summary = await summarize_fn(old_summary, to_compress)

    pipe = r.pipeline()
    pipe.set(_k_summary(session_id), new_summary, ex=settings.memory.stm_ttl_seconds)
    # 老消息已经被摘要承接了,从 list 里删掉,只留 recent
    pipe.delete(_k_turns(session_id))
    if keep_raw:
        pipe.rpush(_k_turns(session_id), *keep_raw)
        pipe.expire(_k_turns(session_id), settings.memory.stm_ttl_seconds)
    await pipe.execute()

    logger.info(
        f"stm.summary_refreshed sid={session_id} compressed={len(to_compress)} "
        f"kept={len(keep_raw)} tokens_before={total_tokens}"
    )
    return True


async def set_slot(session_id: str, key: str, value: Any) -> None:
    """写入会话槽位 —— value 自动 JSON 序列化以便存数字 / dict / list。"""
    r = get_redis()
    pipe = r.pipeline()
    pipe.hset(_k_slots(session_id), key, json.dumps(value, ensure_ascii=False))
    pipe.expire(_k_slots(session_id), settings.memory.stm_ttl_seconds)
    await pipe.execute()


async def get_slots(session_id: str) -> dict[str, Any]:
    """取所有会话槽位 —— 反序列化为 dict[str, Any]。"""
    r = get_redis()
    raw = await r.hgetall(_k_slots(session_id))
    out: dict[str, Any] = {}
    for k, v in raw.items():
        try:
            out[k] = json.loads(v)
        except json.JSONDecodeError:
            out[k] = v
    return out


async def clear_session(session_id: str) -> None:
    """清掉一个会话的所有短期记忆 —— 用于 /logout 或显式重启对话。"""
    r = get_redis()
    await r.delete(
        _k_turns(session_id),
        _k_summary(session_id),
        _k_slots(session_id),
        _k_turn_count(session_id),
    )
