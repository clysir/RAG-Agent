"""长期记忆 —— 用户级离散事实抽取 + 检索。

依据 Mem0 (arXiv 2504.19413):
- 抽取阶段:LLM 读最近用户/助手消息,产出 ADD / UPDATE / INVALIDATE / NOOP 操作列表
- 应用阶段:写 MySQL user_memories(双时态),同步嵌入到 Milvus user_facts_v1
- 检索阶段:user_id 强制过滤(分区键),BGE-M3 嵌入查询,score 阈值过滤,只返回 valid_to IS NULL

API 边界:
- extract_facts():给 LLM 抽事实,纯 IO,无副作用
- apply_facts():把抽取结果落库 + 入向量库
- retrieve_facts():给定用户和 query,返回相关事实
- forget_fact():用户主动忘记(隐私),valid_to=now() 软删,Milvus 物理删除向量

不在这里做:
- LLM 抽取的调度(Celery 任务负责异步触发)
- 状态机集成(state_machine.py 负责调 retrieve_facts)
- API 暴露(app/api/memory.py 负责)
"""

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import with_latency
from config import settings
from db import FactType, SessionLocal, UserMemory
from providers import get_llm, get_text_embedder
from providers.llm.base import Message
from rag.milvus_client import delete_user_fact, search_user_facts, upsert_user_fact

# ============ 抽取阶段数据结构 ============

FactOpType = Literal["ADD", "UPDATE", "INVALIDATE", "NOOP"]


class FactOp(BaseModel):
    """LLM 抽取产出的单条事实操作。

    schema 设计参考 Mem0:
    - ADD:全新事实
    - UPDATE:与已有事实矛盾,新事实生效 + 旧事实 invalidate
    - INVALIDATE:用户主动撤回(如 "我不再吃素了")
    - NOOP:闲聊/无信息,跳过
    """

    operation: FactOpType
    fact_type: FactType
    fact_text: str = ""
    target_fact_id: int | None = Field(
        None, description="UPDATE/INVALIDATE 时指向被影响的旧事实 id"
    )
    confidence: float = Field(0.8, ge=0.0, le=1.0)
    reason: str = Field("", description="可选,LLM 给出的依据,记日志便于排查")


class FactExtractionResult(BaseModel):
    """LLM 一次抽取返回的批操作。"""

    ops: list[FactOp] = Field(default_factory=list)


# ============ 抽取 ============

_EXTRACT_SYSTEM_PROMPT = """你是电商导购 Agent 的"用户事实抽取器"。

任务:从用户与助手的对话片段中,提炼可长期记忆的用户事实(偏好、尺码、品牌、预算、过敏、场景等)。
**严格输出 JSON**,无任何额外文字,格式:
{"ops": [{"operation": "ADD|UPDATE|INVALIDATE|NOOP", "fact_type": "preference|size|brand|budget|allergy|address|occasion|order_history|return_history|other", "fact_text": "...", "target_fact_id": null, "confidence": 0.0-1.0, "reason": "..."}]}

规则:
1. 一句话 = 多条独立事实就拆多条(例如"我穿 L 码,预算 500 以内"→ size + budget 两条 ADD)
2. 与"已有事实列表"矛盾的写 UPDATE,target_fact_id 指向旧事实 id;同时输出对应 INVALIDATE
3. 用户明确说"忘记我之前说的 X"→ INVALIDATE
4. 闲聊、问候、无明确事实 → ops 为空数组,不要硬挤事实
5. confidence:用户主动陈述 ≥ 0.85,助手推断 ≤ 0.6
6. fact_text 用第三人称中文,不要"我",例如"偏好极简风格,不喜欢印花"
7. 不抽取敏感隐私(身份证、密码、银行卡)"""


def _build_extract_messages(
    recent_dialog: list[dict[str, str]],
    existing_facts: list[dict[str, Any]],
) -> list[Message]:
    """构造抽取 prompt。"""
    user_block = (
        "【最近对话】\n"
        + "\n".join(f"{t['role']}: {t['content']}" for t in recent_dialog)
        + "\n\n【已有事实列表(用于判断矛盾)】\n"
        + (
            "\n".join(
                f"id={f['id']} type={f['fact_type']} text={f['fact_text']}"
                for f in existing_facts
            )
            if existing_facts
            else "(无)"
        )
        + "\n\n严格输出 JSON,不要解释。"
    )
    return [
        Message(role="system", content=_EXTRACT_SYSTEM_PROMPT),
        Message(role="user", content=user_block),
    ]


@with_latency("memory.extract")
async def extract_facts(
    user_id: int,
    recent_dialog: list[dict[str, str]],
) -> FactExtractionResult:
    """让 LLM 从最近对话中抽事实。

    Args:
        user_id: 用户 ID,用于查"已有事实列表"做矛盾检测
        recent_dialog: list[{role, content}],近期对话片段
    """
    if not recent_dialog:
        return FactExtractionResult()

    # 先把现有有效事实查出来,作为矛盾检测上下文(最多 20 条避免膨胀)
    async with SessionLocal() as session:
        stmt = (
            select(UserMemory)
            .where(UserMemory.user_id == user_id, UserMemory.valid_to.is_(None))
            .order_by(UserMemory.created_at.desc())
            .limit(20)
        )
        existing = (await session.execute(stmt)).scalars().all()
    existing_dicts = [
        {"id": f.id, "fact_type": f.fact_type.value, "fact_text": f.fact_text}
        for f in existing
    ]

    llm = get_llm()
    msgs = _build_extract_messages(recent_dialog, existing_dicts)
    # 抽取要求确定性高,temperature 调低
    resp = await llm.chat(msgs, stream=False, temperature=0.1, max_tokens=1024)
    raw = resp.content.strip() if hasattr(resp, "content") else ""

    # LLM 偶尔会包 markdown,容错剥离
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()

    try:
        data = json.loads(raw)
        result = FactExtractionResult.model_validate(data)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"memory.extract.parse_fail user_id={user_id} err={e} raw={raw[:200]}")
        return FactExtractionResult()

    logger.info(f"memory.extract user_id={user_id} ops={len(result.ops)}")
    return result


# ============ 应用 ============


def _fact_vector_id(user_id: int, fact_text: str) -> int:
    """事实向量 ID —— sha256(user_id+text+model+version),与商品向量同思路保幂等。"""
    model = settings.embedding.model
    ver = settings.embedding.version_tag
    payload = f"u{user_id}|{fact_text}|{model}|{ver}".encode()
    digest = hashlib.sha256(payload).hexdigest()[:16]
    return int(digest, 16) & 0x7FFFFFFFFFFFFFFF


async def _add_fact_row(
    session: AsyncSession,
    user_id: int,
    op: FactOp,
    source_msg_id: int | None,
    vector_id: int,
) -> UserMemory:
    row = UserMemory(
        user_id=user_id,
        fact_type=op.fact_type,
        fact_text=op.fact_text,
        source_msg_id=source_msg_id,
        confidence=op.confidence,
        vector_id=vector_id,
    )
    session.add(row)
    await session.flush()  # 拿到自增 id
    return row


async def _invalidate_fact_row(session: AsyncSession, fact_id: int) -> UserMemory | None:
    """软删除 —— 设 valid_to=now()。同步删 Milvus 向量。"""
    fact = await session.get(UserMemory, fact_id)
    if fact is None or fact.valid_to is not None:
        return None
    fact.valid_to = datetime.now(timezone.utc)
    await session.flush()
    return fact


@with_latency("memory.apply_facts")
async def apply_facts(
    user_id: int,
    result: FactExtractionResult,
    source_msg_id: int | None = None,
) -> dict[str, int]:
    """把抽取结果落地 —— MySQL 双时态 + Milvus 同步。

    幂等:同样的 (user_id, fact_text) 多次 ADD 会因为 vector_id 一致而 Milvus upsert 覆盖,
    但 MySQL 会插重复行。所以这里 ADD 前先按 vector_id 查一遍跳过。
    """
    if not result.ops:
        return {"added": 0, "invalidated": 0, "updated": 0, "skipped": 0}

    embedder = get_text_embedder()
    stats = {"added": 0, "invalidated": 0, "updated": 0, "skipped": 0}
    milvus_writes: list[dict[str, Any]] = []
    milvus_deletes: list[int] = []

    async with SessionLocal() as session:
        for op in result.ops:
            if op.operation == "NOOP" or not op.fact_text.strip():
                stats["skipped"] += 1
                continue

            if op.operation == "INVALIDATE" and op.target_fact_id:
                row = await _invalidate_fact_row(session, op.target_fact_id)
                if row and row.vector_id:
                    milvus_deletes.append(row.vector_id)
                    stats["invalidated"] += 1
                continue

            if op.operation == "UPDATE" and op.target_fact_id:
                # 旧的 invalidate
                old = await _invalidate_fact_row(session, op.target_fact_id)
                if old and old.vector_id:
                    milvus_deletes.append(old.vector_id)
                # 新的 ADD,落到下面统一处理(继续往下走 ADD 分支逻辑)

            # ADD 或 UPDATE 后的新增分支
            vec_id = _fact_vector_id(user_id, op.fact_text)
            # 同向量 ID 已存在(同用户同文本同模型版本)跳过
            exists = await session.execute(
                select(UserMemory.id).where(UserMemory.vector_id == vec_id)
            )
            if exists.scalar_one_or_none():
                stats["skipped"] += 1
                continue

            row = await _add_fact_row(session, user_id, op, source_msg_id, vec_id)
            milvus_writes.append({
                "vector_id": vec_id,
                "user_id": user_id,
                "fact_id": row.id,
                "fact_type": op.fact_type.value,
                "fact_text": op.fact_text,
            })
            if op.operation == "UPDATE":
                stats["updated"] += 1
            else:
                stats["added"] += 1

        await session.commit()

    # MySQL 提交后再同步 Milvus —— 顺序:嵌入 -> upsert -> delete
    if milvus_writes:
        texts = [w["fact_text"] for w in milvus_writes]
        vectors = await embedder.embed_texts(texts)
        # 并发写 Milvus,等全部完成
        await asyncio.gather(*[
            upsert_user_fact(
                vector_id=w["vector_id"],
                user_id=w["user_id"],
                fact_id=w["fact_id"],
                fact_type=w["fact_type"],
                fact_text=w["fact_text"],
                embedding=v,
            )
            for w, v in zip(milvus_writes, vectors)
        ])
    if milvus_deletes:
        await asyncio.gather(*[delete_user_fact(v) for v in milvus_deletes])

    logger.info(
        f"memory.apply user_id={user_id} added={stats['added']} updated={stats['updated']} "
        f"invalidated={stats['invalidated']} skipped={stats['skipped']}"
    )
    return stats


# ============ 检索 ============


class RetrievedFact(BaseModel):
    """检索返回的事实(给状态机/Agent 用)。"""

    fact_id: int
    fact_type: str
    fact_text: str
    score: float
    confidence: float


@with_latency("memory.retrieve")
async def retrieve_facts(
    user_id: int,
    query: str,
    top_k: int | None = None,
    fact_types: list[str] | None = None,
) -> list[RetrievedFact]:
    """检索用户相关事实 —— 仅返回当前有效(valid_to IS NULL)且分数过阈值。

    Args:
        user_id: 强制带,Milvus 走 partition_key 隔离
        query: 通常是用户当前 query 或 intent 描述
        top_k: 默认 settings.memory.ltm_top_k
        fact_types: 可选过滤类型(只查"尺码"等)
    """
    if not settings.memory.ltm_enabled:
        return []
    if not query.strip():
        return []

    top_k = top_k or settings.memory.ltm_top_k
    threshold = settings.memory.ltm_score_threshold

    embedder = get_text_embedder()
    [qvec] = await embedder.embed_texts([query])

    hits = await search_user_facts(
        user_id=user_id, query_vec=qvec, top_k=top_k * 2, fact_types=fact_types,
    )
    if not hits:
        return []

    # 分数阈值过滤
    hits = [h for h in hits if h["score"] >= threshold]
    if not hits:
        return []

    # 二次校验 MySQL:valid_to 必须为 NULL(Milvus 这边没存 valid_to,避免不同步)
    fact_ids = [h["fact_id"] for h in hits]
    async with SessionLocal() as session:
        stmt = select(UserMemory).where(
            UserMemory.id.in_(fact_ids),
            UserMemory.user_id == user_id,  # 双重保险
            UserMemory.valid_to.is_(None),
        )
        rows = {r.id: r for r in (await session.execute(stmt)).scalars().all()}

        # 命中的 fact 顺手更新 last_used_at,decay 用
        if rows:
            now = datetime.now(timezone.utc)
            await session.execute(
                update(UserMemory)
                .where(UserMemory.id.in_(list(rows.keys())))
                .values(last_used_at=now)
            )
            await session.commit()

    out: list[RetrievedFact] = []
    for h in hits:
        row = rows.get(h["fact_id"])
        if not row:
            continue
        out.append(RetrievedFact(
            fact_id=row.id,
            fact_type=row.fact_type.value,
            fact_text=row.fact_text,
            score=h["score"],
            confidence=row.confidence,
        ))
        if len(out) >= top_k:
            break

    logger.info(f"memory.retrieve user_id={user_id} hits={len(out)} top_score={out[0].score if out else 0:.3f}")
    return out


# ============ 用户主动 forget ============


@with_latency("memory.forget")
async def forget_fact(user_id: int, fact_id: int) -> bool:
    """用户主动 forget —— valid_to=now() + 删 Milvus 向量。

    返回 True 表示删除成功,False 表示该事实不属于此用户或已失效。
    """
    async with SessionLocal() as session:
        fact = await session.get(UserMemory, fact_id)
        if not fact or fact.user_id != user_id:
            return False
        if fact.valid_to is not None:
            return False  # 已失效
        fact.valid_to = datetime.now(timezone.utc)
        vec = fact.vector_id
        await session.commit()

    if vec:
        await delete_user_fact(vec)
    logger.info(f"memory.forget user_id={user_id} fact_id={fact_id}")
    return True


@with_latency("memory.forget_all")
async def forget_all(user_id: int) -> int:
    """删除用户所有事实 —— 隐私退出 / GDPR 风格的"全部忘记"。

    返回删除条数。
    """
    async with SessionLocal() as session:
        stmt = select(UserMemory).where(
            UserMemory.user_id == user_id, UserMemory.valid_to.is_(None)
        )
        rows = (await session.execute(stmt)).scalars().all()
        if not rows:
            return 0
        now = datetime.now(timezone.utc)
        vec_ids = [r.vector_id for r in rows if r.vector_id]
        for r in rows:
            r.valid_to = now
        await session.commit()

    if vec_ids:
        await asyncio.gather(*[delete_user_fact(v) for v in vec_ids])

    logger.info(f"memory.forget_all user_id={user_id} count={len(rows)}")
    return len(rows)
