"""聊天接口 —— SSE 流式输出,Agent 事件序列化成 NDJSON 推给前端。

设计:
- query 必填,image_object_key 可选(先 /upload/image 拿 key 再传过来)
- 登录用户走 get_current_user_optional 拿 user,游客也允许聊天(电商场景常见)
- session_id 由前端管理,首次会话自行 UUID
"""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from agent import AgentContext, stream_agent
from app.core.auth import get_current_user_optional
from db import User, get_session
from providers import get_storage

router = APIRouter()


@router.post("/chat")
async def chat(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User | None, Depends(get_current_user_optional)],
    session_id: str = Form(..., description="前端管理的会话 UUID"),
    query: str = Form(..., min_length=1, max_length=2000),
    image_object_key: str | None = Form(None, description="可选,先调 /upload/image 拿到"),
):
    """流式聊天端点。

    前端用法:
        const formData = new FormData()
        formData.append('session_id', uuid)
        formData.append('query', '帮我找一双通勤鞋')
        formData.append('image_object_key', uploadKey)  // 可选
        const resp = await fetch('/chat', { method: 'POST', body: formData,
                                            headers: { Authorization: 'Bearer ' + token } })
        // 然后用 EventSource 风格解析 SSE
    """
    trace_id = getattr(request.state, "trace_id", "-")

    # 如果带了图片 key,从对象存储拉字节给 Agent 用
    image_bytes: bytes | None = None
    if image_object_key:
        storage = get_storage()
        try:
            image_bytes = await storage.get(image_object_key)
        except FileNotFoundError:
            # 图不存在不致命,降级到纯文本检索
            image_bytes = None

    ctx = AgentContext(
        trace_id=trace_id,
        session_id=session_id,
        user_query=query,
        image_bytes=image_bytes,
    )
    # 运行时依赖:DB session 给 RetrieveTool 用,user 留作个性化扩展
    ctx.extra["session"] = session
    ctx.extra["user"] = user

    async def event_stream():
        async for event in stream_agent(ctx):
            payload = event.model_dump(mode="json")
            yield {"data": json.dumps(payload, ensure_ascii=False)}

    return EventSourceResponse(event_stream())
