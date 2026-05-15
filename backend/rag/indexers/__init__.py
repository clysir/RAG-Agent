"""离线建索引流水线 —— 把商品数据灌入 Milvus,带去重和父子块。

通常由 Celery 任务调用,也可命令行直接跑(scripts/build_index.py)。

流程:
1. 读 MySQL 商品 -> 拼标题+描述+属性
2. 父子块切分
3. 子块 -> 生成 vector_id -> 查 Milvus 是否已存在 -> 不存在则 embedding -> 入库
4. 父块文本另存(简化版直接落 MySQL 的 product 表 / 单独父块表)
"""

from typing import Any

from loguru import logger

from app.core import with_latency
from config import settings
from providers import get_image_embedder, get_storage, get_text_embedder
from rag.indexers.chunking import Chunk, split_parent_child
from rag.indexers.dedup import make_vector_id


@with_latency("indexer.index_product_text")
async def index_product_text(
    product_id: int, title: str, description: str, attributes: dict[str, Any] | None = None
) -> dict[str, int]:
    """把单条商品的文本入库 —— 返回 {inserted, skipped} 统计。

    Args:
        product_id: 商品在 MySQL 的主键,作为 source 标识
        title: 商品标题
        description: 商品描述
        attributes: 商品扩展属性(品牌/材质等),拼到向量化文本里
    """
    # 1. 拼接全文 —— 标题加权放前面,描述紧随,属性扁平化
    parts = [title or ""]
    if description:
        parts.append(description)
    if attributes:
        attr_str = " ".join(f"{k}:{v}" for k, v in attributes.items())
        parts.append(attr_str)
    full_text = "\n".join(p for p in parts if p)
    if not full_text:
        return {"inserted": 0, "skipped": 0}

    # 2. 父子块切分
    _parents, children = split_parent_child(full_text)
    if not children:
        return {"inserted": 0, "skipped": 0}

    # 3. 生成 vector_id 并过滤已存在的(去重)
    embedder = get_text_embedder()
    model_name = settings.embedding.model
    model_version = settings.embedding.version_tag
    source_key = f"product:{product_id}"

    vector_ids: list[int] = [
        make_vector_id(c.content, source_key, model_name, model_version, c.chunk_index)
        for c in children
    ]
    existing = await _query_existing_ids(vector_ids)
    to_insert: list[tuple[int, Chunk]] = [
        (vid, c) for vid, c in zip(vector_ids, children) if vid not in existing
    ]
    if not to_insert:
        logger.debug(f"index.skip_all product_id={product_id} count={len(children)}")
        return {"inserted": 0, "skipped": len(children)}

    # 4. 只对新增内容做 embedding,节省时间
    texts = [c.content for _, c in to_insert]
    vectors = await embedder.embed_texts(texts)

    # 5. 写入 Milvus
    await _insert_text_vectors(
        product_id=product_id,
        items=[
            {
                "vector_id": vid,
                "product_id": product_id,
                "parent_index": c.parent_index,
                "text": c.content,
                "embedding": vec,
            }
            for (vid, c), vec in zip(to_insert, vectors)
        ],
    )
    logger.info(
        f"index.product_text product_id={product_id} "
        f"inserted={len(to_insert)} skipped={len(children) - len(to_insert)}"
    )
    return {"inserted": len(to_insert), "skipped": len(children) - len(to_insert)}


async def _query_existing_ids(ids: list[int]) -> set[int]:
    """查 Milvus 主键存在性 —— 返回已存在的 ID 集合。"""
    import asyncio

    from pymilvus import Collection

    from rag.milvus_client import _connect

    _connect()
    coll = Collection(settings.milvus.text_collection)
    # 用 query 接口按主键查;只返回 ID 字段省带宽
    expr = f"vector_id in {ids}"
    res = await asyncio.to_thread(coll.query, expr=expr, output_fields=["vector_id"])
    return {r["vector_id"] for r in res}


async def _insert_text_vectors(product_id: int, items: list[dict[str, Any]]) -> None:
    """批量写 Milvus 文本 collection —— 用 upsert 防重(主键冲突时覆盖)。"""
    import asyncio

    from pymilvus import Collection

    from rag.milvus_client import _connect

    _connect()
    coll = Collection(settings.milvus.text_collection)
    # pymilvus 期望按字段列的 list-of-list,而不是 list-of-dict
    data = [
        [it["vector_id"] for it in items],
        [it["product_id"] for it in items],
        [it["parent_index"] for it in items],
        [it["text"] for it in items],
        [it["embedding"] for it in items],
    ]
    await asyncio.to_thread(coll.upsert, data)
    await asyncio.to_thread(coll.flush)


# ============ 图像入库 ============


@with_latency("indexer.index_product_image")
async def index_product_image(product_id: int, image_object_key: str) -> dict[str, int]:
    """把商品图像入库 —— object_key 从存储取字节,过 CLIP 后落 Milvus image collection。

    Args:
        product_id: 商品 ID,与 text collection 共享,便于回查
        image_object_key: 对象存储里的 key(local_fs/MinIO/S3 抽象)

    Returns:
        {"inserted": 0/1, "skipped": 0/1}
    """
    # 1. 用 object_key 做 vector_id 输入 —— 同一张图换模型才会重算
    model_name = settings.mm_embedding.model
    model_version = settings.mm_embedding.version_tag
    source_key = f"product_image:{product_id}"
    vector_id = make_vector_id(image_object_key, source_key, model_name, model_version, 0)

    # 2. 去重:已存在直接 skip
    existing = await _query_existing_image_ids([vector_id])
    if vector_id in existing:
        return {"inserted": 0, "skipped": 1}

    # 3. 从存储取图片字节 -> CLIP -> 向量
    storage = get_storage()
    try:
        img_bytes = await storage.get(image_object_key)
    except FileNotFoundError:
        logger.warning(f"index.image.missing product_id={product_id} key={image_object_key}")
        return {"inserted": 0, "skipped": 1}

    embedder = get_image_embedder()
    vectors = await embedder.embed_images([img_bytes])

    # 4. 写 Milvus
    await _insert_image_vectors([
        {
            "vector_id": vector_id,
            "product_id": product_id,
            "image_url": image_object_key,
            "embedding": vectors[0],
        }
    ])
    return {"inserted": 1, "skipped": 0}


async def _query_existing_image_ids(ids: list[int]) -> set[int]:
    """查 Milvus image collection 主键存在性。"""
    import asyncio

    from pymilvus import Collection

    from rag.milvus_client import _connect

    _connect()
    coll = Collection(settings.milvus.image_collection)
    expr = f"vector_id in {ids}"
    res = await asyncio.to_thread(coll.query, expr=expr, output_fields=["vector_id"])
    return {r["vector_id"] for r in res}


async def _insert_image_vectors(items: list[dict[str, Any]]) -> None:
    """批量写 image collection。"""
    import asyncio

    from pymilvus import Collection

    from rag.milvus_client import _connect

    _connect()
    coll = Collection(settings.milvus.image_collection)
    data = [
        [it["vector_id"] for it in items],
        [it["product_id"] for it in items],
        [it["image_url"] for it in items],
        [it["embedding"] for it in items],
    ]
    await asyncio.to_thread(coll.upsert, data)
    await asyncio.to_thread(coll.flush)
