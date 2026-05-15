"""图片检索路 —— 用户上传图片时走这条路。

策略(2026 业界主流):
- 图 + 文混合 query 时,图过 CLIP 得 image_vec,在图像 collection 召回
- 同时把文本 query 也走文本路;最后 RRF 融合
- 没有 LLM caption 也能跑(轻量),但召回质量更好时建议加 VLM 生 caption 走文本路
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rag.types import ProductCandidate
from app.core import with_latency
from config import settings
from db.models import Product
from providers import get_image_embedder
from rag.milvus_client import search_image


@with_latency("rag.image_search")
async def image_search(
    image_bytes: bytes,
    session: AsyncSession,
    top_k: int | None = None,
) -> list[ProductCandidate]:
    """以图搜图入口 —— 返回视觉相似商品。"""
    if not image_bytes:
        return []
    top_k = top_k or settings.retrieval.dense_top_k

    embedder = get_image_embedder()
    [vec] = await embedder.embed_images([image_bytes])
    hits = await search_image(vec, top_k=top_k)
    if not hits:
        return []

    # 图像分数同样需要阈值过滤(余弦/IP 已是 -1~1,IP 归一化向量约 0-1)
    threshold = settings.retrieval.score_threshold
    filtered = [h for h in hits if h["score"] >= threshold]
    if not filtered:
        return []

    product_ids = [h["product_id"] for h in filtered]
    result = await session.execute(select(Product).where(Product.id.in_(product_ids)))
    products = {p.id: p for p in result.scalars().all()}

    out: list[ProductCandidate] = []
    for h in filtered:
        p = products.get(h["product_id"])
        if p is None:
            continue
        out.append(
            ProductCandidate(
                product_id=p.id,
                title=p.title,
                score=float(h["score"]),
                snippet="(以图搜图命中)",
                image_url=h.get("image_url") or p.image_object_key,
                price=float(p.price) if p.price is not None else None,
                extra={"category": p.category, "brand": p.brand, "modality": "image"},
            )
        )
    return out
