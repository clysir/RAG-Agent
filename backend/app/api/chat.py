"""聊天接口 —— SSE 流式输出 + 历史会话查询。

设计:
- POST /chat 走 multipart/form-data,因为要支持可选图片
- 登录用户的对话会同步写入 sessions / messages 表 → 给 /chat/sessions 历史侧栏用
- 匿名(游客)对话**不持久化**,session_id 仅用于 Redis 短期记忆和当前轮次的上下文

为什么不用 EventSource:
- EventSource 只支持 GET,但我们要 POST + FormData 上图
- 所以前端用 fetch ReadableStream 解 SSE,见 lib/sse.ts
"""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Path, Request, status
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from agent import AgentContext, stream_agent
from app.core.auth import get_current_user, get_current_user_optional
from db import Message as ChatMessage
from db import Session as ChatSession
from db import User, get_session
from providers import get_storage
from schemas.common import APIModel, Envelope

router = APIRouter()


# ============ 历史会话 / 消息 schema ============


class SessionBrief(APIModel):
    """会话简略信息 —— 给左侧栏列表用。"""

    id: str
    title: str | None = None
    message_count: int = 0
    updated_at: str
    created_at: str


class MessageOut(APIModel):
    """单条历史消息 —— role / content / 可选图。"""

    id: int
    role: str  # user / assistant
    content: str
    image_url: str | None = None
    created_at: str


# ============ 持久化辅助 ============


async def _ensure_session_row(
    db: AsyncSession, session_id: str, user_id: int, first_user_query: str
) -> ChatSession:
    """会话不存在则创建,存在则可能更新 title(空 title 时)。"""
    row = await db.get(ChatSession, session_id)
    if row is not None:
        # 强校验:已存在的会话不能跨用户挪 —— 收到别人的 session_id 视作非法
        if row.user_id is not None and row.user_id != user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="session_not_owned")
        if row.user_id is None:
            # 匿名时建的(目前其实不入库,但兼容历史数据),登录后认领
            row.user_id = user_id
        return row

    title = (first_user_query or "").strip()[:40] or None
    row = ChatSession(id=session_id, user_id=user_id, title=title)
    db.add(row)
    await db.flush()
    return row


async def _persist_user_message(
    db: AsyncSession,
    session_id: str,
    content: str,
    image_object_key: str | None,
) -> ChatMessage:
    """写用户消息行。"""
    msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=content,
        image_object_key=image_object_key,
    )
    db.add(msg)
    await db.flush()
    return msg


async def _persist_assistant_message(
    db: AsyncSession, session_id: str, content: str
) -> None:
    """写助手消息行 —— 失败不影响响应。"""
    msg = ChatMessage(session_id=session_id, role="assistant", content=content)
    db.add(msg)
    # 顺便戳一下 session.updated_at,让侧栏排序按最新活跃排
    sess = await db.get(ChatSession, session_id)
    if sess is not None:
        from datetime import datetime, timezone

        sess.updated_at = datetime.now(timezone.utc)
    await db.commit()


# ============ 主接口 ============


@router.post("/chat")
async def chat(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User | None, Depends(get_current_user_optional)],
    session_id: str = Form(..., description="前端管理的会话 UUID"),
    query: str = Form(..., min_length=1, max_length=2000),
    image_object_key: str | None = Form(None, description="可选,先调 /upload/image 拿到"),
):
    """流式聊天端点。"""
    trace_id = getattr(request.state, "trace_id", "-")

    # 如果带了图片 key,从对象存储拉字节给 Agent 用
    image_bytes: bytes | None = None
    if image_object_key:
        storage = get_storage()
        try:
            image_bytes = await storage.get(image_object_key)
        except FileNotFoundError:
            image_bytes = None

    # 登录用户:开流前先 upsert session + 写入用户消息(失败不影响聊天本身)
    persist_enabled = user is not None
    if persist_enabled:
        try:
            await _ensure_session_row(db, session_id, user.id, query)
            await _persist_user_message(db, session_id, query, image_object_key)
            await db.commit()
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning(f"chat.persist_user_fail trace_id={trace_id} err={e}")
            persist_enabled = False
            await db.rollback()

    ctx = AgentContext(
        trace_id=trace_id,
        session_id=session_id,
        user_id=user.id if user else None,
        user_query=query,
        image_bytes=image_bytes,
    )
    ctx.extra["session"] = db
    ctx.extra["user"] = user

    async def event_stream():
        accumulated = ""
        try:
            async for event in stream_agent(ctx):
                if event.type == "token" and event.data:
                    accumulated += str(event.data)
                payload = event.model_dump(mode="json")
                yield {"data": json.dumps(payload, ensure_ascii=False)}
        finally:
            if persist_enabled:
                final_text = ctx.final_answer or accumulated
                if final_text:
                    try:
                        await _persist_assistant_message(db, session_id, final_text)
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            f"chat.persist_assistant_fail trace_id={trace_id} err={e}"
                        )

    return EventSourceResponse(event_stream())


# ============ 历史侧栏接口 ============


@router.get("/chat/sessions", response_model=Envelope[list[SessionBrief]])
async def list_sessions(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: int = 50,
) -> Envelope[list[SessionBrief]]:
    """当前用户的会话列表 —— 按最新活跃倒序。"""
    # 顺手把 message_count 一起拿出来,避免 N+1
    count_subq = (
        select(ChatMessage.session_id, func.count(ChatMessage.id).label("cnt"))
        .group_by(ChatMessage.session_id)
        .subquery()
    )
    stmt = (
        select(ChatSession, count_subq.c.cnt)
        .outerjoin(count_subq, ChatSession.id == count_subq.c.session_id)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.updated_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    items = [
        SessionBrief(
            id=s.id,
            title=s.title,
            message_count=int(cnt or 0),
            updated_at=s.updated_at.isoformat() if s.updated_at else "",
            created_at=s.created_at.isoformat() if s.created_at else "",
        )
        for s, cnt in rows
    ]
    return Envelope[list[SessionBrief]](data=items)


@router.get("/chat/sessions/{session_id}/messages", response_model=Envelope[list[MessageOut]])
async def list_session_messages(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
    session_id: str = Path(..., min_length=1, max_length=64),
    limit: int = 200,
) -> Envelope[list[MessageOut]]:
    """指定会话的全部消息 —— 校验所有权,只能读自己的。"""
    sess = await db.get(ChatSession, session_id)
    if sess is None or sess.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session_not_found")

    rows = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id.asc())
            .limit(limit)
        )
    ).scalars().all()

    storage = get_storage()
    items: list[MessageOut] = []
    for m in rows:
        img_url: str | None = None
        if m.image_object_key:
            try:
                img_url = await storage.presign_url(m.image_object_key)
            except Exception:  # noqa: BLE001
                img_url = None
        items.append(
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                image_url=img_url,
                created_at=m.created_at.isoformat() if m.created_at else "",
            )
        )
    return Envelope[list[MessageOut]](data=items)


@router.delete("/chat/sessions/{session_id}", response_model=Envelope[dict])
async def delete_session(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
    session_id: str = Path(..., min_length=1, max_length=64),
) -> Envelope[dict]:
    """删除整段会话 —— 包括其下所有消息。校验所有权。"""
    sess = await db.get(ChatSession, session_id)
    if sess is None or sess.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session_not_found")

    # 先删消息再删会话,避免外键悬空
    await db.execute(
        ChatMessage.__table__.delete().where(ChatMessage.session_id == session_id)
    )
    await db.delete(sess)
    await db.commit()
    return Envelope[dict](data={"deleted": True, "session_id": session_id})
