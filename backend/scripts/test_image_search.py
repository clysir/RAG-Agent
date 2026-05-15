"""验证图文跨模态关联 —— 拿一张商品图反查 Milvus image collection,
再用 product_id 回查 MySQL 拿标题,证明两路 collection 通过 product_id 联通。

跑法:
    python -m scripts.test_image_search
"""

import asyncio
from pathlib import Path

from loguru import logger
from pymilvus import Collection
from sqlalchemy import select

from config import settings
from db import Product, SessionLocal
from providers import get_image_embedder, get_storage
from rag.milvus_client import _connect


async def _query_image(image_bytes: bytes, top_k: int = 5) -> list[dict]:
    embedder = get_image_embedder()
    vec = (await embedder.embed_images([image_bytes]))[0]

    _connect()
    coll = Collection(settings.milvus.image_collection)
    res = await asyncio.to_thread(
        coll.search,
        data=[vec],
        anns_field="embedding",
        param={"metric_type": "IP", "params": {"nprobe": 16}},
        limit=top_k,
        output_fields=["product_id", "image_url"],
    )
    out = []
    for hit in res[0]:
        out.append({
            "score": float(hit.distance),
            "product_id": int(hit.entity.get("product_id")),
            "image_url": hit.entity.get("image_url"),
        })
    return out


async def _query_text(text: str, top_k: int = 5) -> list[dict]:
    """以文搜图 —— CLIP 文本端 -> 图像 collection,验证跨模态。"""
    embedder = get_image_embedder()
    vec = (await embedder.embed_texts([text]))[0]

    _connect()
    coll = Collection(settings.milvus.image_collection)
    res = await asyncio.to_thread(
        coll.search,
        data=[vec],
        anns_field="embedding",
        param={"metric_type": "IP", "params": {"nprobe": 16}},
        limit=top_k,
        output_fields=["product_id", "image_url"],
    )
    out = []
    for hit in res[0]:
        out.append({
            "score": float(hit.distance),
            "product_id": int(hit.entity.get("product_id")),
            "image_url": hit.entity.get("image_url"),
        })
    return out


async def main() -> None:
    # 1. 拿一个有图的商品(MySQL),验证 image_object_key 与 product_id 配对
    async with SessionLocal() as session:
        stmt = select(Product).where(Product.image_object_key.isnot(None)).limit(3)
        sample_products = (await session.execute(stmt)).scalars().all()
        sample_meta = [(p.id, p.title, p.image_object_key) for p in sample_products]

    if not sample_meta:
        logger.error("MySQL 没有任何带图商品")
        return

    storage = get_storage()

    # 2. 以图搜图 —— 拿样本图 -> 反查 -> 期望 top1 是自己
    print("=" * 70)
    print("Test 1: 以图搜图(同图反查 -> top1 应该是自己,score 接近 1.0)")
    print("=" * 70)
    for pid, title, key in sample_meta:
        img = await storage.get(key)
        hits = await _query_image(img, top_k=3)
        print(f"\n  Query product_id={pid} '{title[:40]}'")
        # 用 product_id 回 MySQL 拿命中商品标题
        hit_pids = [h["product_id"] for h in hits]
        async with SessionLocal() as session:
            stmt = select(Product.id, Product.title).where(Product.id.in_(hit_pids))
            id_to_title = dict((await session.execute(stmt)).all())
        for i, h in enumerate(hits, 1):
            marker = " ← SELF" if h["product_id"] == pid else ""
            t = id_to_title.get(h["product_id"], "?")[:40]
            print(f"    {i}. score={h['score']:.4f} pid={h['product_id']:>5} {t}{marker}")

    # 3. 以文搜图 —— CLIP 跨模态,文本 query 命中图像 collection
    print("\n" + "=" * 70)
    print("Test 2: 以文搜图(CLIP 跨模态,文本进 -> 图像 collection 出)")
    print("=" * 70)
    text_queries = ["雪纺连衣裙", "运动鞋", "笔记本电脑包"]
    for q in text_queries:
        hits = await _query_text(q, top_k=3)
        hit_pids = [h["product_id"] for h in hits]
        async with SessionLocal() as session:
            stmt = select(Product.id, Product.title).where(Product.id.in_(hit_pids))
            id_to_title = dict((await session.execute(stmt)).all())
        print(f"\n  Query: '{q}'")
        for i, h in enumerate(hits, 1):
            t = id_to_title.get(h["product_id"], "?")[:50]
            print(f"    {i}. score={h['score']:.4f} pid={h['product_id']:>5} {t}")

    # 4. 双路联通验证 —— 同一个 product_id 在 text/image 两个 collection 都有
    print("\n" + "=" * 70)
    print("Test 3: 双 collection 共享 product_id(文本命中后能找到对应图)")
    print("=" * 70)
    _connect()
    text_coll = Collection(settings.milvus.text_collection)
    image_coll = Collection(settings.milvus.image_collection)
    # 在文本 collection 找几个 product_id,然后到 image collection 验证存在
    text_sample = await asyncio.to_thread(
        text_coll.query, expr="product_id > 0", output_fields=["product_id"], limit=10
    )
    text_pids = list({r["product_id"] for r in text_sample})[:5]
    print(f"\n  从文本 collection 取 product_ids: {text_pids}")
    for pid in text_pids:
        img_rows = await asyncio.to_thread(
            image_coll.query, expr=f"product_id == {pid}", output_fields=["product_id", "image_url"]
        )
        if img_rows:
            print(f"    ✓ product_id={pid} 在图像 collection 也有({len(img_rows)} 条)")
        else:
            print(f"    ✗ product_id={pid} 仅文本,无图(可能 image_object_key 为空)")


if __name__ == "__main__":
    asyncio.run(main())
