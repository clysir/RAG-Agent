# scripts/ —— 离线脚本

> 灌数据 / 建索引 / 评估 / 测试,独立可跑。

---

## 📋 脚本清单

| 脚本 | 用途 | 典型耗时 |
|------|------|---------|
| `download_models.py` | 预下载 BGE-M3 / CLIP / Reranker(走 hf-mirror) | 5-15 min(看网络) |
| `seed_data.py` | 灌 MUGE 2000 商品到 MySQL,图片落 storage | 2-5 min |
| `build_index.py` | 批量入库到 Milvus(文本 + 图像) | ~ 1 min(GPU) |
| `eval.py` | 跑评估集,算 Recall@K / MRR / latency | 视 query 数 |
| `test_image_search.py` | 图文跨模态联通测试(以图搜图 + 以文搜图) | 30 sec |
| `test_models.py` | provider 工厂全量冒烟 | 1 min |

---

## 🚀 `build_index.py`

```bash
python -m scripts.build_index                       # text + image 全建,默认批次 100
python -m scripts.build_index --text-only           # 只建文本
python -m scripts.build_index --image-only          # 只建图像
python -m scripts.build_index --batch-size 64       # 控制每批大小
python -m scripts.build_index --limit 100           # 只跑前 100 条 debug
```

实现要点:
- `_iter_products(batch_size, limit)` 是异步生成器,分页拉 MySQL,**不**一次读全表
- 文本 + 图像都走 `rag/indexers/batch.py` 的批量接口(单次 upsert,末尾统一 flush)
- 单批失败不阻塞全局(`logger.exception` + 计数)
- 实测:
  - 文本 2000 商品 → 51 秒
  - 图像 1981 张 → 31 秒
  - 老的单条循环要 5.5 小时(差 100~700×)

---

## 🌱 `seed_data.py`

数据源:**MUGE 电商图文检索数据集**(真实淘宝商品标题 + 商品图)。

流程:
1. 读 MUGE jsonl(商品标题、类目、价格)
2. 拼 description(类目 + 价格场景描述)
3. 写 MySQL `products`,带 `merchant_id=系统商家`
4. 下载对应商品图,通过 `StorageProvider.put` 落到 storage,`image_object_key` 写回 MySQL

如要换数据集(Products-10K / 自爬),只需提供同样 schema 的 jsonl。

---

## 📊 `eval.py`

输入:`tests/eval_queries.jsonl`,每行
```json
{"query": "适合通勤的双肩包", "expected_product_ids": [123, 456], "category": "服饰"}
```

跑法:
```bash
python -m scripts.eval                              # 默认 top_k=10
python -m scripts.eval --file other.jsonl
python -m scripts.eval --top-k 20
python -m scripts.eval --concurrent 4               # 并发 query 数
python -m scripts.eval --output report.json         # 落盘详细报告
```

指标:
- **Recall@K**:expected 中至少一个进入 top-K 的比例(K=1/5/10/20)
- **MRR**:1 / best_rank 的平均(没命中=0)
- **Latency**:avg / p50 / p95 / max(ms)

实现:`asyncio.Semaphore` 控并发,失败 query 单独计数不算入分母。

---

## 🖼️ `test_image_search.py`

验证图文双 collection 通过 `product_id` 联通:

1. **Test 1 以图搜图**:取样本商品图反查 image collection,期望 top1 = self(score ≈ 1.0)
2. **Test 2 以文搜图**:CLIP 文本端 → image collection,验证跨模态语义召回(连衣裙→连衣裙)
3. **Test 3 双 collection 对齐**:从 text collection 取 product_id,确认在 image collection 也存在

跑法:
```bash
python -m scripts.test_image_search
```

预期输出:
```
Test 1: 以图搜图(同图反查 -> top1 应该是自己,score 接近 1.0)
  Query product_id=1 '落地式台盆柜'
    1. score=1.0003 pid=    1 落地式台盆柜 ← SELF
    2. score=0.8258 pid=  556 书架胡桃木
    ...
Test 3: 双 collection 共享 product_id
  ✓ product_id=768 在图像 collection 也有
  ...
```

---

## 🧪 `test_models.py`

provider 工厂冒烟测试:
- LLM 一发一收
- 文本 embedding,断言维度 = 1024
- 图像 embedding,断言维度 = 512
- Rerank,断言分数列表长度对得上
- Vision(若启用),断言返回非空 caption

跑法:
```bash
python -m scripts.test_models
```

无 API key 的 provider 自动跳过(不报错)。

---

## 📥 `download_models.py`

预下载所有本地模型到 HuggingFace cache,走 hf-mirror:

```bash
python -m scripts.download_models
```

下载清单:
- `BAAI/bge-m3`(~ 2GB)
- `OFA-Sys/chinese-clip-vit-base-patch16`(~ 700MB)
- `BAAI/bge-reranker-v2-m3`(~ 2.3GB)

下载后 `HF_HUB_OFFLINE=1` 自动生效,后续运行不再联网。
