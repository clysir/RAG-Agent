"""Milvus 客户端封装 —— 文本和图像两个 collection 分别管理。

设计要点:
1. 用 pymilvus 的同步 SDK,通过 asyncio.to_thread 适配到协程
2. collection schema 由 settings 决定向量维度,切换 embedding 模型只改 .env
3. 商品 ID 作为主键,与 MySQL 的 products.id 一一对应
"""

import asyncio
from typing import Any

from loguru import logger
from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from config import settings


def _connect() -> None:
    """建立 Milvus 连接 —— alias 默认即可,只连一次。"""
    if "default" not in connections.list_connections():
        connections.connect(
            alias="default",
            host=settings.milvus.host,
            port=str(settings.milvus.port),
        )
        logger.info(
            f"milvus.connect host={settings.milvus.host}:{settings.milvus.port}"
        )


def _build_text_schema() -> CollectionSchema:
    """文本 collection schema —— 主键 vector_id(hash),关联 product_id,父子块结构。"""
    fields = [
        # vector_id 是 hash 出来的稳定 ID,实现幂等去重;不再用 auto_id
        FieldSchema(name="vector_id", dtype=DataType.INT64, is_primary=True),
        FieldSchema(name="product_id", dtype=DataType.INT64, description="商品 ID,回查 MySQL 用"),
        FieldSchema(
            name="parent_index", dtype=DataType.INT64,
            description="所属父块索引,命中后用于回查父块上下文",
        ),
        FieldSchema(
            name="text", dtype=DataType.VARCHAR, max_length=2048,
            description="向量化所用的子块原文,便于排查",
        ),
        FieldSchema(
            name="embedding", dtype=DataType.FLOAT_VECTOR, dim=settings.milvus.text_dim
        ),
    ]
    return CollectionSchema(fields, description="商品文本向量 collection(父子块结构)")


def _build_image_schema() -> CollectionSchema:
    """图像 collection schema —— 一个商品多张图,vector_id 用 hash(url+模型)。"""
    fields = [
        FieldSchema(name="vector_id", dtype=DataType.INT64, is_primary=True),
        FieldSchema(name="product_id", dtype=DataType.INT64),
        FieldSchema(name="image_url", dtype=DataType.VARCHAR, max_length=1024),
        FieldSchema(
            name="embedding", dtype=DataType.FLOAT_VECTOR, dim=settings.milvus.image_dim
        ),
    ]
    return CollectionSchema(fields, description="商品图像向量 collection")


def _build_user_facts_schema() -> CollectionSchema:
    """用户长期事实 collection —— 与商品向量分库,严格按 user_id 隔离。

    设计:
    - user_id 作为 partition_key,Milvus 自动按用户分区,避免跨用户污染(Mem0 / Palo Alto Unit42 强调的隐私要求)
    - fact_id 同 MySQL user_memories.id,删除时双向同步
    - fact_type 入向量库,便于按类型过滤(只查"尺码"事实等)
    - embedding 维度复用文本侧的 BGE-M3 维度
    """
    fields = [
        FieldSchema(name="vector_id", dtype=DataType.INT64, is_primary=True),
        # is_partition_key=True 让 Milvus 自动按 user_id 分区,查询时强制带 user_id 过滤即可硬隔离
        FieldSchema(
            name="user_id", dtype=DataType.INT64,
            description="用户 ID,分区键 + 必填过滤条件",
            is_partition_key=True,
        ),
        FieldSchema(name="fact_id", dtype=DataType.INT64, description="MySQL user_memories.id"),
        FieldSchema(
            name="fact_type", dtype=DataType.VARCHAR, max_length=32,
            description="事实类型枚举,过滤用",
        ),
        FieldSchema(
            name="fact_text", dtype=DataType.VARCHAR, max_length=1024,
            description="事实原文,便于排查",
        ),
        FieldSchema(
            name="embedding", dtype=DataType.FLOAT_VECTOR, dim=settings.milvus.text_dim
        ),
    ]
    return CollectionSchema(
        fields,
        description="用户长期事实向量(BGE-M3 嵌入,user_id 分区)",
        # partition_key 模式下需要显式开启
        partition_key_field="user_id",
    )


def ensure_collections() -> None:
    """启动时调用 —— 不存在则创建,已存在则跳过。同时把所有 collection load 到内存。

    Milvus 要求 query/search/upsert 前必须 load,这里做幂等的 load 一次。
    """
    _connect()

    text_name = settings.milvus.text_collection
    if not utility.has_collection(text_name):
        coll = Collection(text_name, _build_text_schema())
        # IVF_FLAT + IP(内积)适合归一化后的稠密向量,生产可换 HNSW
        coll.create_index(
            field_name="embedding",
            index_params={
                "index_type": "IVF_FLAT",
                "metric_type": "IP",
                "params": {"nlist": 1024},
            },
        )
        logger.info(f"milvus.collection_created name={text_name}")

    image_name = settings.milvus.image_collection
    if not utility.has_collection(image_name):
        coll = Collection(image_name, _build_image_schema())
        coll.create_index(
            field_name="embedding",
            index_params={
                "index_type": "IVF_FLAT",
                "metric_type": "IP",
                "params": {"nlist": 1024},
            },
        )
        logger.info(f"milvus.collection_created name={image_name}")

    facts_name = settings.milvus.user_facts_collection
    if not utility.has_collection(facts_name):
        coll = Collection(facts_name, _build_user_facts_schema())
        coll.create_index(
            field_name="embedding",
            index_params={
                "index_type": "IVF_FLAT",
                "metric_type": "IP",
                "params": {"nlist": 256},  # 用户事实量级远小于商品,nlist 小一点
            },
        )
        logger.info(f"milvus.collection_created name={facts_name}")

    # 全部 load 到内存 —— Milvus 要求 query/search/upsert 前必须 load
    for name in (text_name, image_name, facts_name):
        try:
            Collection(name).load()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"milvus.collection_load_failed name={name} err={e}")


async def search_text(query_vec: list[float], top_k: int = 20) -> list[dict[str, Any]]:
    """在文本 collection 做向量检索 —— 返回带 product_id/parent_index 和分数的命中。"""
    _connect()
    coll = Collection(settings.milvus.text_collection)
    res = await asyncio.to_thread(
        coll.search,
        data=[query_vec],
        anns_field="embedding",
        param={"metric_type": "IP", "params": {"nprobe": 16}},
        limit=top_k,
        output_fields=["product_id", "parent_index", "text"],
    )
    hits = res[0]
    return [
        {
            "product_id": h.entity.get("product_id"),
            "parent_index": h.entity.get("parent_index"),
            "text": h.entity.get("text"),
            "score": h.score,
        }
        for h in hits
    ]


async def search_image(query_vec: list[float], top_k: int = 20) -> list[dict[str, Any]]:
    """在图像 collection 做以图搜图。"""
    _connect()
    coll = Collection(settings.milvus.image_collection)
    res = await asyncio.to_thread(
        coll.search,
        data=[query_vec],
        anns_field="embedding",
        param={"metric_type": "IP", "params": {"nprobe": 16}},
        limit=top_k,
        output_fields=["product_id", "image_url"],
    )
    hits = res[0]
    return [
        {
            "product_id": h.entity.get("product_id"),
            "image_url": h.entity.get("image_url"),
            "score": h.score,
        }
        for h in hits
    ]


async def search_user_facts(
    user_id: int,
    query_vec: list[float],
    top_k: int = 5,
    fact_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    """在用户事实 collection 检索 —— 强制按 user_id 过滤,可选按 fact_type 收窄。

    Args:
        user_id: 必填,Milvus 走 partition key 隔离
        query_vec: 查询向量(BGE-M3 嵌入用户当前 query 或 intent 描述)
        top_k: 返回前 N 条最相关事实
        fact_types: 可选,只查特定类型(如 ["size", "budget"])
    """
    _connect()
    coll = Collection(settings.milvus.user_facts_collection)
    # 表达式必须带 user_id,即便 partition 已隔离也再保险一层
    expr_parts = [f"user_id == {user_id}"]
    if fact_types:
        types_lit = ",".join(f'"{t}"' for t in fact_types)
        expr_parts.append(f"fact_type in [{types_lit}]")
    expr = " && ".join(expr_parts)

    res = await asyncio.to_thread(
        coll.search,
        data=[query_vec],
        anns_field="embedding",
        param={"metric_type": "IP", "params": {"nprobe": 8}},
        limit=top_k,
        expr=expr,
        output_fields=["fact_id", "user_id", "fact_type", "fact_text"],
    )
    hits = res[0]
    return [
        {
            "fact_id": h.entity.get("fact_id"),
            "user_id": h.entity.get("user_id"),
            "fact_type": h.entity.get("fact_type"),
            "fact_text": h.entity.get("fact_text"),
            "score": h.score,
        }
        for h in hits
    ]


async def upsert_user_fact(
    *,
    vector_id: int,
    user_id: int,
    fact_id: int,
    fact_type: str,
    fact_text: str,
    embedding: list[float],
) -> None:
    """写入/更新单条用户事实向量。"""
    _connect()
    coll = Collection(settings.milvus.user_facts_collection)
    data = [
        [vector_id],
        [user_id],
        [fact_id],
        [fact_type],
        [fact_text[:1024]],
        [embedding],
    ]
    await asyncio.to_thread(coll.upsert, data)
    await asyncio.to_thread(coll.flush)


async def delete_user_fact(vector_id: int) -> None:
    """按 vector_id 物理删除事实向量 —— 用于用户主动 forget 场景。"""
    _connect()
    coll = Collection(settings.milvus.user_facts_collection)
    await asyncio.to_thread(coll.delete, expr=f"vector_id == {vector_id}")
    await asyncio.to_thread(coll.flush)
