"""离线建索引脚本 —— 把 MySQL products 灌入 Milvus(文本 + 图像两个 collection)。

工程级:
- 批量处理:N 个商品的所有子块合并 -> 一次 embed -> 一次 upsert,大幅减 Milvus 往返
- 失败重试:单批失败不阻塞全局
- 进度日志:每批输出统计
- 全部结束后 1 次 flush

用法:
  python -m scripts.build_index                     # text + image 全建,默认批次 100
  python -m scripts.build_index --text-only         # 只建文本
  python -m scripts.build_index --image-only        # 只建图像
  python -m scripts.build_index --batch-size 200    # 控制每批大小
  python -m scripts.build_index --limit 100         # 只处理前 100 条(debug)
"""

import argparse
import asyncio
import time

from loguru import logger
from sqlalchemy import select

from db import Product, SessionLocal
from rag.indexers.batch import (
    batch_index_products_image,
    batch_index_products_text,
    flush_image_collection,
    flush_text_collection,
)
from rag.milvus_client import ensure_collections


async def _iter_products(batch_size: int, limit: int):
    """分页拉 products,每次 yield 一个 batch。"""
    offset = 0
    fetched = 0
    while True:
        async with SessionLocal() as session:
            stmt = (
                select(Product)
                .order_by(Product.id)
                .offset(offset)
                .limit(batch_size)
            )
            rows = (await session.execute(stmt)).scalars().all()
        if not rows:
            return
        out = []
        for p in rows:
            out.append({
                "id": p.id,
                "title": p.title,
                "description": p.description or "",
                "attributes": None,  # 后续解析 JSON,目前 seed 数据无此字段
                "image_object_key": p.image_object_key,
            })
            fetched += 1
            if limit and fetched >= limit:
                yield out
                return
        yield out
        offset += batch_size


async def _build_text_index(batch_size: int, limit: int) -> dict[str, int]:
    """批量文本索引,全部跑完后 flush 一次。"""
    text_inserted = text_skipped = 0
    failed = 0
    n_batches = 0
    started = time.time()

    async for batch in _iter_products(batch_size, limit):
        n_batches += 1
        try:
            stats = await batch_index_products_text(batch)
            text_inserted += stats["inserted"]
            text_skipped += stats["skipped"]
        except Exception as e:  # noqa: BLE001
            failed += 1
            logger.exception(f"batch_index.fail batch_no={n_batches} err={e}")
        elapsed = time.time() - started
        logger.info(
            f"build_index.text_progress batch={n_batches} products_done={n_batches * batch_size} "
            f"inserted_total={text_inserted} rate={text_inserted / max(elapsed, 1e-6):.1f}/s"
        )

    await flush_text_collection()
    return {"inserted": text_inserted, "skipped": text_skipped, "failed": failed}


async def _build_image_index(batch_size: int, limit: int) -> dict[str, int]:
    """批量图像索引 —— 并发取图 + 一次 CLIP batch embed + 一次 upsert,末尾统一 flush。"""
    inserted = skipped = missing = failed = 0
    n_batches = 0
    started = time.time()

    async for batch in _iter_products(batch_size, limit):
        n_batches += 1
        try:
            stats = await batch_index_products_image(batch)
            inserted += stats["inserted"]
            skipped += stats["skipped"]
            missing += stats["missing"]
        except Exception as e:  # noqa: BLE001
            failed += 1
            logger.exception(f"batch_image_index.fail batch_no={n_batches} err={e}")
        elapsed = time.time() - started
        logger.info(
            f"build_index.image_progress batch={n_batches} products_done={n_batches * batch_size} "
            f"inserted_total={inserted} missing={missing} rate={inserted / max(elapsed, 1e-6):.1f}/s"
        )

    await flush_image_collection()
    return {"inserted": inserted, "skipped": skipped, "missing": missing, "failed": failed}


async def main(batch_size: int, limit: int, do_text: bool, do_image: bool) -> None:
    await asyncio.to_thread(ensure_collections)

    text_stats = {"inserted": 0, "skipped": 0, "failed": 0}
    image_stats = {"inserted": 0, "skipped": 0, "missing": 0, "failed": 0}
    started = time.time()

    if do_text:
        text_stats = await _build_text_index(batch_size, limit)
    if do_image:
        image_stats = await _build_image_index(batch_size, limit)

    elapsed = time.time() - started
    logger.info(
        f"build_index.done elapsed={elapsed:.1f}s "
        f"text_inserted={text_stats['inserted']} text_skipped={text_stats['skipped']} text_failed={text_stats['failed']} "
        f"image_inserted={image_stats['inserted']} image_skipped={image_stats['skipped']} "
        f"image_missing={image_stats['missing']} image_failed={image_stats['failed']}"
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="把 MySQL products 批量灌进 Milvus")
    p.add_argument("--batch-size", type=int, default=100, help="批次大小(商品数)")
    p.add_argument("--limit", type=int, default=0, help="只处理前 N 条,0 = 全部")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--text-only", action="store_true", help="只建文本索引")
    mode.add_argument("--image-only", action="store_true", help="只建图像索引")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(
        main(
            batch_size=args.batch_size,
            limit=args.limit,
            do_text=not args.image_only,
            do_image=not args.text_only,
        )
    )
