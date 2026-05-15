"""用户记忆 API —— 查看 / 删除自己的长期事实。

PIPL / GDPR 友好:用户应当能审计 Agent 记住了什么,并随时单删 / 全删。

路由:
- GET    /memory/                列出当前用户的有效事实
- GET    /memory/all              列出所有事实(含已失效的)管理面板用
- DELETE /memory/{fact_id}        软删除单条事实(valid_to=now + 删 Milvus 向量)
- POST   /memory/forget-all       一键全部忘记(谨慎)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.memory import forget_all as memory_forget_all
from app.core.memory import forget_fact as memory_forget_fact
from db import User, UserMemory, get_session
from schemas import Envelope

router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryItem(BaseModel):
    """对外暴露的记忆条目。"""

    id: int
    fact_type: str
    fact_text: str
    confidence: float
    valid_from: str
    valid_to: str | None
    source_msg_id: int | None = None


class MemoryList(BaseModel):
    items: list[MemoryItem] = Field(default_factory=list)
    total: int = 0


def _to_item(row: UserMemory) -> MemoryItem:
    return MemoryItem(
        id=row.id,
        fact_type=row.fact_type.value,
        fact_text=row.fact_text,
        confidence=row.confidence,
        valid_from=row.valid_from.isoformat(),
        valid_to=row.valid_to.isoformat() if row.valid_to else None,
        source_msg_id=row.source_msg_id,
    )


@router.get("/", response_model=Envelope[MemoryList])
async def list_my_memories(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(50, ge=1, le=200),
    fact_type: str | None = Query(None, description="可选,只查指定类型"),
) -> Envelope[MemoryList]:
    """列出当前用户的有效长期事实(valid_to IS NULL)。"""
    stmt = (
        select(UserMemory)
        .where(UserMemory.user_id == user.id, UserMemory.valid_to.is_(None))
        .order_by(UserMemory.last_used_at.desc())
        .limit(limit)
    )
    if fact_type:
        stmt = stmt.where(UserMemory.fact_type == fact_type)
    rows = (await session.execute(stmt)).scalars().all()
    return Envelope[MemoryList](
        data=MemoryList(items=[_to_item(r) for r in rows], total=len(rows))
    )


@router.get("/all", response_model=Envelope[MemoryList])
async def list_all_my_memories(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(200, ge=1, le=500),
) -> Envelope[MemoryList]:
    """列出当前用户全部事实(含已失效),便于管理面板审计。"""
    stmt = (
        select(UserMemory)
        .where(UserMemory.user_id == user.id)
        .order_by(UserMemory.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return Envelope[MemoryList](
        data=MemoryList(items=[_to_item(r) for r in rows], total=len(rows))
    )


@router.delete("/{fact_id}", response_model=Envelope[dict])
async def forget_one(
    fact_id: int,
    user: Annotated[User, Depends(get_current_user)],
) -> Envelope[dict]:
    """软删除单条事实 —— valid_to=now() + 同步删 Milvus 向量。

    幂等:已失效的再删返回 404。
    """
    ok = await memory_forget_fact(user.id, fact_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="memory_not_found")
    return Envelope[dict](data={"deleted": True, "fact_id": fact_id})


@router.post("/forget-all", response_model=Envelope[dict])
async def forget_everything(
    user: Annotated[User, Depends(get_current_user)],
) -> Envelope[dict]:
    """一键忘记当前用户所有事实 —— GDPR / PIPL 风格的退出选项。

    操作不可恢复(老事实仍以 valid_to 标记在 MySQL,但 Milvus 向量被物理删除,
    无法再被检索;若需完全删除可走 DBA 工单清 user_memories 行)。
    """
    count = await memory_forget_all(user.id)
    return Envelope[dict](data={"invalidated": count})
