"""批量索引器 —— 跨商品批量做 embedding + 一次 upsert,大幅减少 Milvus 往返。

工程级优化:
- 老的 index_product_text / index_product_image 一商品一 flush,
  Milvus 每次 flush 触发 segment seal,平均 10 秒,严重拖慢
- 新版本:N 个商品的所有子块/图像合并 -> 一次 embed -> 一次 upsert
- 全部批次跑完后调用 flush_*_collection() 显式 flush 一次
- 通过批量 _query 提前去重,主键 hash 一致时跳过
"""

import asyncio
from typing import Any

from loguru import logger
from pymilvus import Collection

from app.core import with_latency
from config import settings
from providers import get_image_embedder, get_storage, get_text_embedder
from rag.indexers.chunking import split_parent_child
from rag.indexers.dedup import make_vector_id
from rag.milvus_client import _connect


@with_latency("indexer.batch_index_products_text")
async def batch_index_products_text(
    products: list[dict[str, Any]],
) -> dict[str, int]:
    """批量入库 —— 输入 [{id, title, description, attributes}],一次 upsert + flush。

    比单条循环快 50-100 倍(避免每商品 flush)。

    Args:
        products: 字段需含 id / title / description(可空) / attributes(可空 dict)

    Returns:
        {inserted, skipped, products}
    """
    if not products:
        return {"inserted": 0, "skipped": 0, "products": 0}

    model_name = settings.embedding.model
    model_version = settings.embedding.version_tag

    # 1. 切块 + 生成 vector_id —— 把所有商品的所有子块合并到一张大表
    all_items: list[dict[str, Any]] = []
    for p in products:
        title = p.get("title") or ""
        desc = p.get("description") or ""
        attrs = p.get("attributes") or {}
        attr_str = " ".join(f"{k}:{v}" for k, v in attrs.items()) if attrs else ""
        full_text = "\n".join(s for s in [title, desc, attr_str] if s)
        if not full_text:
            continue
        _parents, children = split_parent_child(full_text)
        if not children:
            continue
        pid = p["id"]
        source_key = f"product:{pid}"
        for c in children:
            vid = make_vector_id(c.content, source_key, model_name, model_version, c.chunk_index)
            all_items.append({
                "vector_id": vid,
                "product_id": pid,
                "parent_index": c.parent_index,
                "text": c.content,
            })

    if not all_items:
        return {"inserted": 0, "skipped": 0, "products": len(products)}

    # 2. 批量去重 —— 一次查 Milvus 拿全部已存在 ID
    _connect()
    coll = Collection(settings.milvus.text_collection)
    ids = [it["vector_id"] for it in all_items]
    # 大 IN 表达式分片避免超过 Milvus 单 expr 长度限制
    existing: set[int] = set()
    chunk = 500
    for i in range(0, len(ids), chunk):
        sub = ids[i : i + chunk]
        expr = f"vector_id in {sub}"
        res = await asyncio.to_thread(coll.query, expr=expr, output_fields=["vector_id"])
        existing.update(r["vector_id"] for r in res)

    to_insert = [it for it in all_items if it["vector_id"] not in existing]
    skipped = len(all_items) - len(to_insert)
    if not to_insert:
        logger.info(f"batch_index.all_existing products={len(products)} skipped={skipped}")
        return {"inserted": 0, "skipped": skipped, "products": len(products)}

    # 3. 批量 embedding —— BGE-M3 内部 batch_size 由模型决定,我们这边一次喂多条
    embedder = get_text_embedder()
    texts = [it["text"] for it in to_insert]
    vectors = await embedder.embed_texts(texts)

    # 4. 一次 upsert,Milvus 列式格式
    data = [
        [it["vector_id"] for it in to_insert],
        [it["product_id"] for it in to_insert],
        [it["parent_index"] for it in to_insert],
        [it["text"] for it in to_insert],
        vectors,
    ]
    await asyncio.to_thread(coll.upsert, data)
    # 不在批次内 flush,留到 batch 全部结束统一一次 flush
    logger.info(
        f"batch_index.inserted products={len(products)} chunks={len(to_insert)} "
        f"skipped={skipped}"
    )
    return {"inserted": len(to_insert), "skipped": skipped, "products": len(products)}


async def flush_text_collection() -> None:
    """显式 flush 文本 collection —— 全部批次跑完后调用一次。"""
    _connect()
    coll = Collection(settings.milvus.text_collection)
    await asyncio.to_thread(coll.flush)
    logger.info("batch_index.flushed collection=product_text")


# ============ 图像批量入库 ============


@with_latency("indexer.batch_index_products_image")
async def batch_index_products_image(
    products: list[dict[str, Any]],
    fetch_concurrency: int = 16,
) -> dict[str, int]:
    """批量图像入库 —— 并发取图 + 一次 CLIP embed + 一次 upsert。

    瓶颈拆解:
    - 取图 IO:并发 fetch_concurrency 路并行,默认 16(本地 fs 也吃 CPU 解码,不宜过大)
    - CLIP forward:GPU 上单次 batch 推理远比 N 次单图快(我们的实现接受 list[bytes])
    - Milvus 写入:一次 upsert,跳过 per-product flush

    Args:
        products: 字段需含 id / image_object_key(可空,空则跳过)
        fetch_concurrency: 并发拉图数,默认 16

    Returns:
        {inserted, skipped, missing, products}
    """
    if not products:
        return {"inserted": 0, "skipped": 0, "missing": 0, "products": 0}

    model_name = settings.mm_embedding.model
    model_version = settings.mm_embedding.version_tag

    # 1. 生成 (vector_id, product_id, object_key) 三元组,过滤无图商品
    items: list[dict[str, Any]] = []
    for p in products:
        key = p.get("image_object_key")
        if not key:
            continue
        pid = p["id"]
        source_key = f"product_image:{pid}"
        vid = make_vector_id(key, source_key, model_name, model_version, 0)
        items.append({"vector_id": vid, "product_id": pid, "image_object_key": key})

    if not items:
        return {"inserted": 0, "skipped": 0, "missing": 0, "products": len(products)}

    # 2. 批量去重 —— 同 text,分片查 Milvus
    _connect()
    coll = Collection(settings.milvus.image_collection)
    ids = [it["vector_id"] for it in items]
    existing: set[int] = set()
    chunk = 500
    for i in range(0, len(ids), chunk):
        sub = ids[i : i + chunk]
        expr = f"vector_id in {sub}"
        res = await asyncio.to_thread(coll.query, expr=expr, output_fields=["vector_id"])
        existing.update(r["vector_id"] for r in res)

    to_fetch = [it for it in items if it["vector_id"] not in existing]
    skipped = len(items) - len(to_fetch)
    if not to_fetch:
        logger.info(f"batch_index.image.all_existing products={len(products)} skipped={skipped}")
        return {"inserted": 0, "skipped": skipped, "missing": 0, "products": len(products)}

    # 3. 并发拉图 —— Semaphore 控并发,FileNotFound 标 missing
    storage = get_storage()
    sem = asyncio.Semaphore(fetch_concurrency)

    async def _fetch(it: dict[str, Any]) -> tuple[dict[str, Any], bytes | None]:
        async with sem:
            try:
                return it, await storage.get(it["image_object_key"])
            except FileNotFoundError:
                return it, None
            except Exception as e:  # noqa: BLE001
                logger.warning(f"batch_index.image.fetch_fail key={it['image_object_key']} err={e}")
                return it, None

    results = await asyncio.gather(*(_fetch(it) for it in to_fetch))

    fetched: list[dict[str, Any]] = []
    fetched_bytes: list[bytes] = []
    missing = 0
    for it, b in results:
        if b is None:
            missing += 1
            continue
        fetched.append(it)
        fetched_bytes.append(b)

    if not fetched:
        logger.warning(f"batch_index.image.no_bytes products={len(products)} missing={missing}")
        return {"inserted": 0, "skipped": skipped, "missing": missing, "products": len(products)}

    # 4. CLIP 一次性 embed —— batch 内一次前向,GPU 利用率高
    embedder = get_image_embedder()
    vectors = await embedder.embed_images(fetched_bytes)

    # 5. 一次 upsert,Milvus 列式
    data = [
        [it["vector_id"] for it in fetched],
        [it["product_id"] for it in fetched],
        [it["image_object_key"] for it in fetched],
        vectors,
    ]
    await asyncio.to_thread(coll.upsert, data)

    logger.info(
        f"batch_index.image.inserted products={len(products)} images={len(fetched)} "
        f"skipped={skipped} missing={missing}"
    )
    return {
        "inserted": len(fetched),
        "skipped": skipped,
        "missing": missing,
        "products": len(products),
    }


async def flush_image_collection() -> None:
    """显式 flush 图像 collection —— 全部批次跑完后调用一次。"""
    _connect()
    coll = Collection(settings.milvus.image_collection)
    await asyncio.to_thread(coll.flush)
    logger.info("batch_index.flushed collection=product_image")
