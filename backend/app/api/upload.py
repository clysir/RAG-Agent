"""上传路由 —— 用户/商家上传图片到对象存储,返回 object_key 供后续接口引用。

这是图文导购的关键基础设施 —— 用户上传图片做以图搜图、商家上传商品图都走这个。
"""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.auth import get_current_user_optional
from db import User
from providers import get_storage
from schemas import Envelope, UploadResponse

router = APIRouter(prefix="/upload", tags=["upload"])

# 业务约束:只允许图片,限制大小;PDF/视频等未来再拓展白名单
_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_MAX_BYTES = 10 * 1024 * 1024  # 10MB


@router.post("/image", response_model=Envelope[UploadResponse])
async def upload_image(
    file: Annotated[UploadFile, File(..., description="图片文件")],
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> Envelope[UploadResponse]:
    """上传图片 —— 游客也能上传(用于以图搜图),登录用户的 key 会带 user_id 便于审计。"""
    if file.content_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"unsupported_content_type: {file.content_type}",
        )

    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="file_too_large"
        )
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="empty_file")

    # 生成 object_key:user 区分 + 随机短 token + 原扩展名
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if file.filename else "bin"
    if len(ext) > 8 or not ext.isalnum():
        ext = "bin"
    owner = f"user_{user.id}" if user else "guest"
    key = f"uploads/{owner}/{secrets.token_urlsafe(8)}.{ext}"

    storage = get_storage()
    await storage.put(key, data, content_type=file.content_type)
    url = await storage.presign_url(key)

    return Envelope[UploadResponse](
        data=UploadResponse(
            object_key=key,
            url=url,
            size=len(data),
            content_type=file.content_type,
        )
    )
