"""管理员路由 —— 审核商品、封禁用户。

设计:
- 审核通过 -> 创建 Product 行 + 触发 Celery 入库任务
- 审核驳回 -> 写理由,商家可见,可重新提交
- 封禁用户 -> 翻 status,JWT 不会立即失效但下次受保护接口会 403
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_admin
from db import (
    Product,
    ProductSubmission,
    SubmissionStatus,
    User,
    UserStatus,
    get_session,
)
from schemas import (
    BanUserRequest,
    Envelope,
    RejectSubmissionRequest,
    SubmissionBrief,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/submissions", response_model=Envelope[list[SubmissionBrief]])
async def list_pending_submissions(
    _: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    submission_status: str = "pending",
) -> Envelope[list[SubmissionBrief]]:
    """查看待审核列表 —— 默认 pending,可传 ?submission_status=approved 等查历史。"""
    try:
        sstatus = SubmissionStatus(submission_status)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_status")

    rows = (
        await session.execute(
            select(ProductSubmission)
            .where(ProductSubmission.status == sstatus)
            .order_by(ProductSubmission.created_at.asc())
        )
    ).scalars().all()

    items = [
        SubmissionBrief(
            id=s.id,
            merchant_id=s.merchant_id,
            title=s.title,
            category=s.category,
            price=float(s.price),
            status=s.status.value,
            image_url=None,
            created_at=s.created_at.isoformat(),
        )
        for s in rows
    ]
    return Envelope[list[SubmissionBrief]](data=items)


@router.post("/submissions/{sid}/approve", response_model=Envelope[dict])
async def approve_submission(
    sid: int,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[dict]:
    """通过审核 —— 创建 Product + 触发 Celery 入库。"""
    sub = await session.get(ProductSubmission, sid)
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="submission_not_found")
    if sub.status != SubmissionStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"already_{sub.status.value}")

    product = Product(
        merchant_id=sub.merchant_id,
        title=sub.title,
        category=sub.category,
        brand=sub.brand,
        price=sub.price,
        stock=sub.stock,
        description=sub.description,
        attributes=sub.attributes,
        image_object_key=sub.image_object_key,
    )
    session.add(product)
    await session.flush()  # 拿到 product.id

    sub.status = SubmissionStatus.APPROVED
    sub.reviewer_id = admin.id
    sub.approved_product_id = product.id
    await session.commit()

    # 异步入库 —— 不阻塞接口响应
    from app.workers.tasks import build_index_for_product

    build_index_for_product.delay(product.id)

    return Envelope[dict](data={"product_id": product.id, "submission_id": sub.id})


@router.post("/submissions/{sid}/reject", response_model=Envelope[dict])
async def reject_submission(
    sid: int,
    payload: RejectSubmissionRequest,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[dict]:
    """驳回 —— 写理由。"""
    sub = await session.get(ProductSubmission, sid)
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="submission_not_found")
    if sub.status != SubmissionStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"already_{sub.status.value}")

    sub.status = SubmissionStatus.REJECTED
    sub.reviewer_id = admin.id
    sub.reject_reason = payload.reason
    await session.commit()
    return Envelope[dict](data={"submission_id": sub.id})


@router.post("/users/{uid}/ban", response_model=Envelope[dict])
async def ban_user(
    uid: int,
    payload: BanUserRequest,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[dict]:
    """封禁用户 —— 下次受保护接口会 403。"""
    user = await session.get(User, uid)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="user_not_found")
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="cannot_ban_self")
    user.status = UserStatus.BANNED
    await session.commit()
    return Envelope[dict](data={"user_id": user.id, "status": user.status.value})


@router.post("/users/{uid}/unban", response_model=Envelope[dict])
async def unban_user(
    uid: int,
    _: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[dict]:
    """解封用户。"""
    user = await session.get(User, uid)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="user_not_found")
    user.status = UserStatus.ACTIVE
    await session.commit()
    return Envelope[dict](data={"user_id": user.id, "status": user.status.value})
