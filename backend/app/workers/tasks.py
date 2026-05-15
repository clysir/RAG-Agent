"""Celery 任务集合 —— 重活都在这里跑,在线请求路径不阻塞。

任务清单:
- build_index_for_product: 单商品入库(切块+embedding+upsert)
- rebuild_bm25_index: 全量重建 BM25 索引
- batch_index_products: 批量入库,内部调度 build_index_for_product
- extract_user_facts: 从对话片段抽取用户长期事实并落库
- decay_user_memories: 定时清理无读命中的过期事实
"""

import asyncio

from loguru import logger

from app.workers.celery_app import celery_app


@celery_app.task(name="rag.build_index_for_product", bind=True, max_retries=3)
def build_index_for_product(self, product_id: int) -> dict:
    """单商品入库 —— 同步入口,内部跑 async 任务。

    出错自动重试 3 次,指数退避避免雪崩。
    """
    import json as _json

    from sqlalchemy import select

    from db import SessionLocal, Product
    from rag.indexers import index_product_text

    async def _run():
        async with SessionLocal() as session:
            p = await session.scalar(select(Product).where(Product.id == product_id))
            if p is None:
                return {"inserted": 0, "skipped": 0, "missing": True}
            # 把 attributes JSON 解析成 dict 喂给 indexer,使品牌/材质等参数也被向量化
            attrs: dict | None = None
            if p.attributes:
                try:
                    parsed = _json.loads(p.attributes)
                    if isinstance(parsed, dict):
                        attrs = parsed
                    else:
                        logger.warning(
                            f"build_index.attrs_not_dict product_id={product_id} type={type(parsed).__name__}"
                        )
                except _json.JSONDecodeError as e:
                    logger.warning(f"build_index.attrs_bad_json product_id={product_id} err={e}")
            return await index_product_text(
                product_id=p.id,
                title=p.title,
                description=p.description or "",
                attributes=attrs,
            )

    try:
        return asyncio.run(_run())
    except Exception as e:
        logger.exception(f"celery.build_index_failed product_id={product_id}")
        raise self.retry(exc=e, countdown=2 ** self.request.retries)


@celery_app.task(name="rag.rebuild_bm25_index")
def rebuild_bm25_index() -> dict:
    """全量重建 BM25 索引 —— 启动后或商品大批量变更后调一次。"""
    from sqlalchemy import select

    from db import SessionLocal, Product
    from rag.retrievers.bm25 import get_bm25_index

    async def _run():
        async with SessionLocal() as session:
            rows = (await session.execute(select(Product))).scalars().all()
            items = [
                (p.id, " ".join(filter(None, [p.title, p.description, p.brand or ""])))
                for p in rows
            ]
        return items

    items = asyncio.run(_run())
    get_bm25_index().rebuild(items)
    return {"docs": len(items)}


@celery_app.task(name="rag.batch_index_products")
def batch_index_products(product_ids: list[int]) -> dict:
    """批量入库 —— fan-out 到单任务,便于并行和失败重试粒度。"""
    for pid in product_ids:
        build_index_for_product.delay(pid)
    return {"dispatched": len(product_ids)}


# ============ 记忆相关任务 ============


@celery_app.task(name="memory.extract_user_facts", bind=True, max_retries=2)
def extract_user_facts(
    self,
    user_id: int,
    recent_dialog: list[dict],
    source_msg_id: int | None = None,
) -> dict:
    """从最近对话片段抽取用户长期事实 —— Agent RESPOND 完成后异步触发。

    工业实践 (Mem0):抽取走异步而非每轮同步,read 路径保持低延迟,
    write 路径延迟几秒可接受。

    Args:
        user_id: 必填,事实归属
        recent_dialog: [{"role": "user|assistant", "content": "..."}]
                       通常是本轮 user_msg + assistant_msg,可包含上一轮做矛盾检测
        source_msg_id: 可选,本轮 assistant message 在 MySQL 的 id,便于追溯
    """
    from app.core.memory import apply_facts, extract_facts

    async def _run():
        result = await extract_facts(user_id, recent_dialog)
        return await apply_facts(user_id, result, source_msg_id=source_msg_id)

    try:
        stats = asyncio.run(_run())
        logger.info(
            f"celery.extract_user_facts user_id={user_id} "
            f"added={stats.get('added', 0)} updated={stats.get('updated', 0)} "
            f"invalidated={stats.get('invalidated', 0)} skipped={stats.get('skipped', 0)}"
        )
        return stats
    except Exception as e:
        logger.exception(f"celery.extract_user_facts_failed user_id={user_id}")
        # 抽取失败不重试太激进,2 次足够避免假死
        raise self.retry(exc=e, countdown=10 * (self.request.retries + 1))


@celery_app.task(name="memory.decay_user_memories")
def decay_user_memories() -> dict:
    """定时失效长期无读命中的事实 —— Celery beat 调度,默认每日跑。

    规则:last_used_at 早于 (now - LTM_DECAY_DAYS) 的 valid_to IS NULL 事实,
    标记 valid_to=now() + 同步删 Milvus 向量。
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from config import settings
    from db import SessionLocal, UserMemory
    from rag.milvus_client import delete_user_fact

    async def _run():
        threshold = datetime.now(timezone.utc) - timedelta(days=settings.memory.ltm_decay_days)
        async with SessionLocal() as session:
            stmt = select(UserMemory).where(
                UserMemory.valid_to.is_(None),
                UserMemory.last_used_at < threshold,
            )
            rows = (await session.execute(stmt)).scalars().all()
            if not rows:
                return 0
            now = datetime.now(timezone.utc)
            vec_ids = [r.vector_id for r in rows if r.vector_id]
            for r in rows:
                r.valid_to = now
            await session.commit()
        for v in vec_ids:
            await delete_user_fact(v)
        return len(rows)

    count = asyncio.run(_run())
    logger.info(f"celery.decay_user_memories invalidated={count}")
    return {"invalidated": count}
