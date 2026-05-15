"""混合检索器 —— Query 优化 + 多路召回 + RRF 融合 + Rerank + 阈值过滤。

整体流程:
    queries = optimize_query(user_query, history)
    for q in queries:
        dense_hits  = milvus 向量召回
        sparse_hits = BM25 召回(可关)
        per_query_results.append(rrf([dense, sparse]))
    fused = rrf(per_query_results)
    reranked = rerank(user_query, fused) -> 过滤分数 < threshold
    候选 + MySQL 结构化过滤 -> 返回 ProductCandidate

接口对 Agent 层透明,Agent 只调 hybrid_search(user_query, history, session)。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rag.types import ProductCandidate
from app.core import with_latency
from config import settings
from db.models import Product
from providers import get_reranker, get_text_embedder
from rag.milvus_client import search_text
from rag.query_optimizer import optimize_query
from rag.retrievers.bm25 import get_bm25_index
from rag.retrievers.fusion import rrf_fuse


@with_latency("rag.hybrid_search")
async def hybrid_search(
    query: str,
    session: AsyncSession,
    history: list[dict[str, str]] | None = None,
    category: str | None = None,
    max_price: float | None = None,
) -> list[ProductCandidate]:
    """混合检索入口 —— 返回带元数据、已过阈值的商品候选列表。"""

    cfg = settings.retrieval

    # 1. Query 优化
    queries = await optimize_query(query, history)

    # 2. 每个 query 各自跑多路召回,然后第一层 RRF 合并到 per-query 结果
    per_query_fused: list[list[dict]] = []
    embedder = get_text_embedder()

    # 批量 embedding 所有 query 节省调用次数
    vecs = await embedder.embed_texts(queries)

    bm25 = get_bm25_index() if cfg.enable_bm25 else None

    for q, vec in zip(queries, vecs):
        dense = await search_text(vec, top_k=cfg.dense_top_k)
        paths = [dense]
        if bm25 is not None:
            sparse = bm25.search(q, top_k=cfg.sparse_top_k)
            paths.append(sparse)
        per_query_fused.append(rrf_fuse(paths, k=cfg.rrf_k, top_k=cfg.fusion_top_k))

    # 3. 第二层 RRF —— 把多个 query 的结果再融合一次
    fused = rrf_fuse(per_query_fused, k=cfg.rrf_k, top_k=cfg.fusion_top_k)
    if not fused:
        return []

    # 4. Rerank —— 用原始用户 query 与候选做精排
    candidates_text = [h.get("text", "") or "" for h in fused]
    reranker = get_reranker()
    ranked = await reranker.rerank(query, candidates_text, top_k=settings.rerank.top_k)
    # ranked: [(index, score)]

    # 5. 分数阈值过滤 —— 防引用噪声
    threshold = cfg.score_threshold
    kept = [(i, s) for i, s in ranked if s >= threshold]
    if not kept:
        return []  # 上游 Agent 走 NEED_CLARIFY 或诚实告知

    # 6. 取回 MySQL 完整字段 + 结构化过滤
    selected = [fused[i] for i, _ in kept]
    product_ids = [h["product_id"] for h in selected]
    stmt = select(Product).where(Product.id.in_(product_ids))
    if category:
        stmt = stmt.where(Product.category == category)
    if max_price is not None:
        stmt = stmt.where(Product.price <= max_price)
    result = await session.execute(stmt)
    products = {p.id: p for p in result.scalars().all()}

    # 7. 按 rerank 顺序拼装
    candidates: list[ProductCandidate] = []
    for (i, score), hit in zip(kept, selected):
        p = products.get(hit["product_id"])
        if p is None:
            continue  # 被结构化过滤掉
        candidates.append(
            ProductCandidate(
                product_id=p.id,
                title=p.title,
                score=float(score),
                snippet=(hit.get("text") or "")[:200],
                image_url=p.image_object_key,
                price=float(p.price) if p.price is not None else None,
                extra={
                    "category": p.category,
                    "brand": p.brand,
                    "rating": float(p.rating or 0),
                    "sources": hit.get("sources", []),
                },
            )
        )
    return candidates