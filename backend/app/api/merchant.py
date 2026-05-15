"""商家路由 —— 上传商品(进审核队列)。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_merchant
from db import ProductSubmission, SubmissionStatus, User, get_session
from providers import get_storage
from schemas import Envelope, SubmissionBrief, SubmitProductRequest

router = APIRouter(prefix="/merchant", tags=["merchant"])


@router.post("/products", response_model=Envelope[SubmissionBrief])
async def submit_product(
    payload: SubmitProductRequest,
    user: Annotated[User, Depends(require_merchant)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[SubmissionBrief]:
    """商家提交商品 —— 不直接进 products 表,进 product_submissions 待审核。"""
    sub = ProductSubmission(
        merchant_id=user.id,
        title=payload.title,
        category=payload.category,
        price=payload.price,
        brand=payload.brand,
        description=payload.description,
        stock=payload.stock,
        image_object_key=payload.image_object_key,
        status=SubmissionStatus.PENDING,
    )
    session.add(sub)
    await session.commit()
    await session.refresh(sub)

    storage = get_storage()
    image_url = (
        await storage.presign_url(sub.image_object_key) if sub.image_object_key else None
    )
    return Envelope[SubmissionBrief](
        data=SubmissionBrief(
            id=sub.id,
            merchant_id=sub.merchant_id,
            title=sub.title,
            category=sub.category,
            price=float(sub.price),
            status=sub.status.value,
            image_url=image_url,
            created_at=sub.created_at.isoformat(),
        )
    )


@router.get("/products", response_model=Envelope[list[SubmissionBrief]])
async def list_my_submissions(
    user: Annotated[User, Depends(require_merchant)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[list[SubmissionBrief]]:
    """查看自己的提交历史 —— 含审核状态。"""
    rows = (
        await session.execute(
            select(ProductSubmission)
            .where(ProductSubmission.merchant_id == user.id)
            .order_by(ProductSubmission.created_at.desc())
        )
    ).scalars().all()

    storage = get_storage()
    items = []
    for s in rows:
        url = await storage.presign_url(s.image_object_key) if s.image_object_key else None
        items.append(
            SubmissionBrief(
                id=s.id,
                merchant_id=s.merchant_id,
                title=s.title,
                category=s.category,
                price=float(s.price),
                status=s.status.value,
                image_url=url,
                created_at=s.created_at.isoformat(),
            )
        )
    return Envelope[list[SubmissionBrief]](data=items)
