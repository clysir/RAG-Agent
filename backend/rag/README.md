# rag/ —— RAG 核心:索引 + 检索 + Query 优化

> 不依赖 `app` / `agent`,纯算法层。被 agent 工具调用。

---

## 📂 结构

```
rag/
├── milvus_client.py    # 连接 + ensure_collections(3 个 collection 的 schema)
├── types.py            # ProductCandidate(放这里避免 rag→agent 反向 import)
├── indexers/           # 离线建库
├── retrievers/         # 在线召回 + 融合
└── query_optimizer/    # query 改写 / HyDE / MultiQuery
```

---

## 🏪 Milvus Collections

| Collection | 维度 | 关键字段 | 索引 |
|-----------|------|---------|------|
| `product_text` | 1024 (BGE-M3) | `vector_id` (PK), `product_id`, `parent_index`, `text` | IVF_FLAT, IP |
| `product_image` | 512 (CLIP) | `vector_id` (PK), `product_id`, `image_url` | IVF_FLAT, IP |
| `user_facts_v1` | 1024 (BGE-M3) | `vector_id` (PK), `user_id` (`is_partition_key=True`), `fact_type`, `fact_text` | IVF_FLAT, IP |

两个 product collection 通过 `product_id` 关联回 MySQL `products` 表 —— 这是图文双路在召回后聚合的关键。

`user_facts_v1` 用 partition_key 做**硬隔离**:每次 search 必须传 `user_id` 表达式,只走自己分区,杜绝串户。

---

## 🏗️ 离线索引(`rag/indexers/`)

```
indexers/
├── __init__.py         # 单条接口 index_product_text / index_product_image(保留用于增量)
├── batch.py            # ★ 批量接口(性能关键)
├── chunking.py         # 父子块切分
└── dedup.py            # vector_id 生成 sha256(content + source + model + chunk_idx)[:16]
```

### 批量入库(`batch.py`)是性能关键

老方式(单条循环):
- 每商品 `coll.upsert + coll.flush`,Milvus segment seal 平均 10 秒/次
- 2000 商品 = 5.5 小时,GPU 利用率 3%(全在等 flush)

batch 方式:
- N 个商品的所有子块合并 → 一次 Milvus query 批量去重(分片 500) → 一次 BGE-M3 batch embed → 一次 upsert
- 全部跑完后 `flush_text_collection()` 显式 flush 一次
- 实测:**文本 2000 商品 51 秒,图像 1981 张 31 秒**

图像 batch 额外做:
- `asyncio.Semaphore(fetch_concurrency=16)` 并发拉图(本地 fs 仍吃 CPU 解码)
- CLIP `embed_images(list[bytes])` 单次 forward(GPU 利用率达 90%+)

**新增建索引代码必须批量化,严禁退回单条循环**(CLAUDE.md rule #4)。

### 父子块切分(`chunking.py`)

| 块 | 大小 | 用途 |
|----|------|------|
| 父块 (parent) | 800 char | 命中后回查,喂 LLM 保上下文完整 |
| 子块 (child)  | 200 char | 细粒度向量召回,Recall 更准 |
| overlap       | 50 char  | 防边界信息丢失 |

子块带 `parent_index`,Milvus 命中子块后回 MySQL 拿父块。

短文本(< `MIN_CHUNK_THRESHOLD=100`)直接整段入库,不切。

### vector_id 防重(`dedup.py`)

```python
vector_id = sha256(content + source_key + model_name + model_version + chunk_idx).hexdigest()[:16]
```

- 内容变了 → ID 变 → 入库
- 内容不变 → ID 不变 → query existing 命中 → 跳过 embedding
- 模型版本 (`EMBEDDING_VERSION_TAG`) 进 hash,换模型重建不会与旧数据冲突

---

## 🔍 在线检索(`rag/retrievers/`)

```
retrievers/
├── __init__.py         # hybrid_search 主入口
├── dense.py            # Milvus 向量召回(BGE-M3 query → product_text)
├── sparse.py           # BM25 内存版(rank-bm25)
├── fusion.py           # RRF (Reciprocal Rank Fusion)
└── image.py            # 图像召回(CLIP query → product_image)
```

### Hybrid Search 主流程

```python
async def hybrid_search(query, session, category=None, max_price=None) -> list[ProductCandidate]:
    # 1. 多路召回(并行)
    dense_hits  = await dense_search(query, top_k=30)
    sparse_hits = await sparse_search(query, top_k=30) if RETRIEVAL_ENABLE_BM25 else []

    # 2. RRF 融合(RRF_K=60),按 product_id 合并
    fused = rrf_fuse([dense_hits, sparse_hits], k=60)
    candidates = fused[:fusion_top_k]  # top-30

    # 3. 回 MySQL 拿完整商品信息 + 结构化过滤(category / max_price / 库存)
    candidates = await enrich_from_mysql(session, candidates, filters)

    # 4. (调用方继续 cross-encoder rerank + 阈值过滤)
    return candidates
```

### 跨模态调用

带图 query 时:
- `image_search(image_bytes) → product_image collection → product_id 列表`
- 用 product_id 拿对应 text candidates,与文本召回的合并打 RRF
- 这样实现"图文一致性"召回(图像视觉相似 + 文本语义相关)

---

## 🔄 Query 优化(`rag/query_optimizer/`)

按 `.env` 开关三选一或组合:

| 策略 | env 开关 | 实现 |
|------|---------|------|
| Rewrite | `QO_ENABLE_REWRITE` | LLM 改写口语 / 消歧义,返回单条 query |
| HyDE | `QO_ENABLE_HYDE` | LLM 生假设答案,用其向量去检索 |
| MultiQuery | `QO_ENABLE_MULTI_QUERY` | LLM 展开成 N 个角度的 query(`QO_MULTI_QUERY_COUNT=3`) |

`optimize_query(query, ctx) → (rewritten, expanded_list)`,被 `QueryRewriteTool` 调用一次,扩展 query 塞 `ctx.expanded_queries`,后续 `RetrieveTool` 复用,避免双重 LLM 调用浪费。

---

## 📐 ProductCandidate(`types.py`)

```python
class ProductCandidate(BaseModel):
    product_id: int
    title: str
    description: str | None
    price: float | None
    category: str | None
    image_object_key: str | None
    score: float                   # 当前阶段的分数(召回时 RRF / rerank 时 cross-encoder)
    score_source: Literal["dense","sparse","rrf","rerank"]
```

放在 `rag/types.py` 而不是 `agent/context.py`,因为 rag 模块也要构造它返回给 agent;反向 import 会破坏 CLAUDE.md rule #4。

---

## 🧪 验证

```bash
# 离线评估
python -m scripts.eval --top-k 10

# 图文跨模态联通测试
python -m scripts.test_image_search
```
