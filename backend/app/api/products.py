"""商品路由 —— 公开接口,首页 / 详情页 / 筛选都走这里。

不需要登录:
- 浏览商品是电商主页的核心,游客也得能看
- 鉴权放在写接口(商家提交 / 管理员审核)

image_url:
- DB 存的是 object_key(对象存储里的路径)
- 这里走 storage.presign_url() 换出临时可访问 URL
- local_fs provider 返回 "/static/{key}",需要 main.py 挂 StaticFiles
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db import Product, get_session
from providers import get_storage
from schemas.common import APIModel, Envelope
from schemas.product import ProductBrief, ProductDetail

router = APIRouter(prefix="/products", tags=["products"])


class ProductPage(APIModel):
    """商品列表分页响应 —— 扁平字段,跟前端 ProductListResponse 对齐。"""

    items: list[ProductBrief]
    total: int
    page: int
    page_size: int


async def _presign(storage, key: str | None) -> str | None:
    """安全 presign —— key 为空返回 None,异常时降级到 None 而不是 500。"""
    if not key:
        return None
    try:
        return await storage.presign_url(key)
    except Exception:  # noqa: BLE001
        return None


@router.get("", response_model=Envelope[ProductPage])
async def list_products(
    session: Annotated[AsyncSession, Depends(get_session)],
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    q: str | None = Query(None, description="标题关键词模糊匹配"),
    category: str | None = Query(None),
    brand: str | None = Query(None),
    min_price: float | None = Query(None, ge=0),
    max_price: float | None = Query(None, ge=0),
) -> Envelope[ProductPage]:
    """商品列表 —— 结构化筛选 + 简单关键词搜索。

    注:这里的 q 是 MySQL LIKE,不走向量检索。语义检索在 /chat 内部。
    """
    conds = []
    if category:
        conds.append(Product.category == category)
    if brand:
        conds.append(Product.brand == brand)
    if min_price is not None:
        conds.append(Product.price >= min_price)
    if max_price is not None:
        conds.append(Product.price <= max_price)
    if q:
        # 标题 / 描述 任一命中
        like = f"%{q}%"
        conds.append(or_(Product.title.like(like), Product.description.like(like)))

    where_clause = and_(*conds) if conds else None

    # total
    total_stmt = select(func.count(Product.id))
    if where_clause is not None:
        total_stmt = total_stmt.where(where_clause)
    total = (await session.execute(total_stmt)).scalar_one()

    # items
    list_stmt = (
        select(Product).order_by(Product.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    if where_clause is not None:
        list_stmt = list_stmt.where(where_clause)
    rows = (await session.execute(list_stmt)).scalars().all()

    storage = get_storage()
    items: list[ProductBrief] = []
    for p in rows:
        items.append(
            ProductBrief(
                id=p.id,
                title=p.title,
                category=p.category,
                price=float(p.price),
                image_url=await _presign(storage, p.image_object_key),
                rating=float(p.rating) if p.rating is not None else None,
            )
        )

    return Envelope[ProductPage](
        data=ProductPage(items=items, total=total, page=page, page_size=page_size)
    )


@router.get("/categories", response_model=Envelope[list[str]])
async def list_categories(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[list[str]]:
    """商品全部 distinct 类目 —— 给前端筛选下拉用。"""
    rows = (
        await session.execute(
            select(distinct(Product.category)).order_by(Product.category)
        )
    ).scalars().all()
    return Envelope[list[str]](data=[r for r in rows if r])


@router.get("/brands", response_model=Envelope[list[str]])
async def list_brands(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[list[str]]:
    """商品全部 distinct 品牌 —— 给前端筛选下拉用。"""
    rows = (
        await session.execute(
            select(distinct(Product.brand)).where(Product.brand.is_not(None)).order_by(Product.brand)
        )
    ).scalars().all()
    return Envelope[list[str]](data=[r for r in rows if r])


@router.get("/{product_id}", response_model=Envelope[ProductDetail])
async def get_product(
    product_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[ProductDetail]:
    """商品详情 —— 用于 /products/[id] 页。"""
    p = await session.get(Product, product_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="product_not_found")

    storage = get_storage()
    return Envelope[ProductDetail](
        data=ProductDetail(
            id=p.id,
            title=p.title,
            category=p.category,
            price=float(p.price),
            image_url=await _presign(storage, p.image_object_key),
            rating=float(p.rating) if p.rating is not None else None,
            brand=p.brand,
            description=p.description,
            stock=p.stock,
            review_count=p.review_count,
            attributes=None,
        )
    )
