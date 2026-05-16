# RAG-Agent · 后端

> Python 3.11 / FastAPI / SQLAlchemy 2.0 / Milvus 2.4 / Redis / Celery / MinIO

---

## 📐 整体架构

依赖方向**单向**,反向 import 一票否决:

```
app  →  agent  →  rag, providers  →  db, config
```

```
HTTP / SSE
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│  app/  FastAPI 入口                                         │
│   ├─ middleware: trace_id / logging / CORS                  │
│   ├─ api/: chat / auth / products / upload / memory / ...   │
│   ├─ core/: auth(JWT+bcrypt) / memory(STM / LTM 写读路径) │
│   └─ workers/: Celery 任务(extract_user_facts / 衰减 / 建索引) │
└──────────────────┬──────────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  agent/  自研状态机                                         │
│   state_machine.py: 8 个状态 + 路由函数                     │
│   tools/: Intent / MemoryLoad / Vision / QueryRewrite /     │
│           Retrieve / Rerank / Clarify / Respond             │
│   prompts/: prompt 模板                                     │
└──────────────────┬──────────────────────────────────────────┘
                   ▼
┌──────────────────────────┬──────────────────────────────────┐
│  rag/                    │  providers/                      │
│   retrievers/            │   llm/ (deepseek / volcengine /  │
│   indexers/ (batch!)     │         openai)                  │
│   query_optimizer/       │   embedding/ (local_bge /        │
│   types.py(DTO)          │              local_clip)         │
│                          │   rerank/ (local_bge / none)     │
│                          │   vision/ (disabled / 豆包 /     │
│                          │            openai)               │
│                          │   storage/ (minio / s3 / fs)     │
│                          │   sms/ (mock / aliyun / 腾讯)    │
└──────────────────────────┴──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  db/ + config/                                              │
│   db/models/: User / Product / Conversation / Message /     │
│               UserMemory / ProductSubmission                │
│   db/migrations/: Alembic                                   │
│   config/settings.py: 单一配置入口 + _SubSettings 基类      │
└─────────────────────────────────────────────────────────────┘
                   │
                   ▼
   MySQL 8(业务库)│ Milvus 2.4(向量)│ Redis(缓存+broker)│
   MinIO(对象存储)│ Celery beat(定时)
```

---

## 📂 目录约定

| 目录 | 职责 | 详细 |
|------|------|------|
| `app/` | FastAPI 入口、路由、中间件、Celery worker | [`app/README.md`](app/README.md) |
| `agent/` | 自研状态机 Agent + 8 个工具 | [`agent/README.md`](agent/README.md) |
| `rag/` | 检索器 / 索引器 / Query 优化 / 共享 DTO | [`rag/README.md`](rag/README.md) |
| `providers/` | LLM / Embedding / Rerank / Vision / Storage / SMS 协议抽象 | [`providers/README.md`](providers/README.md) |
| `config/` | `pydantic-settings` 单一配置入口 | [`config/README.md`](config/README.md) |
| `db/` | SQLAlchemy ORM + Alembic 迁移 | [`db/README.md`](db/README.md) |
| `schemas/` | Pydantic Request / Response 对外契约 | [`schemas/README.md`](schemas/README.md) |
| `scripts/` | 离线脚本:灌数据 / 建索引 / 评估 / 测试 | [`scripts/README.md`](scripts/README.md) |
| `docker/` | docker-compose + 镜像加速 | [`docker/README.md`](docker/README.md) |
| `tests/` | pytest + 评估集 | — |
| `data/` | MUGE 数据集 + 用户上传(运行时,被 ignore) | — |

---

## 🚀 快速开始

```bash
# 1. Python 环境(3.11+,推荐 3.13)
python -m venv .venv && source .venv/bin/activate
pip install -e ".[embedding-local]"   # 加 [dev] 装 pytest / ruff

# 2. 基础设施
docker compose -f docker/docker-compose.yml up -d

# 3. 配置
cp .env.example .env
# 编辑 .env:填 LLM_API_KEY,确认 MYSQL_PORT=3307(避端口冲突)

# 4. 数据库迁移
alembic upgrade head

# 5. 预下载模型(BGE-M3 / CLIP / Reranker,~4GB,走 hf-mirror)
python -m scripts.download_models

# 6. 灌数据(MUGE 2000 商品 + 图片)
python -m scripts.seed_data

# 7. 建索引(文本 + 图像,各 30-50 秒)
python -m scripts.build_index

# 8. 预置管理员账号(默认 admin / admin123,公开注册接口不允许创建 admin)
python -m scripts.seed_admin

# 9. 启动 API
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
# 或:
python -m app --dev   # 详尽日志 + SQL echo + latency 打印
python -m app --op    # 生产模式:INFO 日志 + CORS 收紧

# 10. 启动 Celery(可选,异步任务)
celery -A app.workers.celery_app worker --loglevel=info
celery -A app.workers.celery_app beat --loglevel=info   # 定时任务
```

打开 `http://localhost:8000/docs` 看 OpenAPI。

> **docker compose 起来只有 3 个容器?** 是镜像问题。旧版用 `quay.io/coreos/etcd`,国内拉不到 → milvus 起不来。
> 现在已切到 `bitnami/etcd:3.5`(dockerhub),并给所有 service 都加了 `restart` + `healthcheck`,
> 用 `condition: service_healthy` 让 milvus 真正等到 etcd/minio 就绪才启动。重新 `up -d` 即可。

### 验证

```bash
# 端到端 SSE
curl -N -X POST http://127.0.0.1:8000/chat \
  -F "session_id=demo-1" \
  -F "query=推荐几款雪纺连衣裙"

# 图文跨模态测试(以图搜图 + 以文搜图 + 双 collection 对齐)
python -m scripts.test_image_search

# 离线评估
python -m scripts.eval --top-k 10

# 健康检查
curl http://127.0.0.1:8000/health
```

---

## 🤖 Agent 状态机契约

```python
class AgentState(str, Enum):
    INTENT             # 意图分类:SEARCH / RECOMMEND / DETAIL / COMPARE / CHITCHAT / ...
    LOAD_MEMORY        # 登录 + 购物意图才进:Redis 短期 + Milvus + MySQL 长期
    IMAGE_UNDERSTAND   # 带图 + Vision Provider 启用时,VLM 生 caption
    QUERY_REWRITE      # 改写 + 可选 HyDE / MultiQuery → ctx.expanded_queries
    RETRIEVE           # 多路召回 + RRF 融合
    RERANK             # cross-encoder 精排 + 阈值过滤
    NEED_CLARIFY       # 召回空 / 全低分:LLM 生成反问,以 token 事件吐出
    RESPOND            # LLM 流式生成,逐 token SSE
    END

# Tool 协议
class Tool(Protocol):
    name: str
    async def execute(self, ctx: AgentContext) -> ToolOutput: ...

# 入口
async def stream_agent(ctx: AgentContext) -> AsyncIterator[AgentEvent]:
    # 进入前:append_turn(session_id, "user", query)
    # 状态循环 → RESPOND 流式 → append_turn("assistant") + 派发 Celery 抽事实
    # NEED_CLARIFY 也吐 token 事件,前端渲染统一
```

路由函数(`_route_after_intent` / `_route_after_memory` / `_route_after_retrieve`)是**纯函数**,易测。

详情见 [`agent/README.md`](agent/README.md)。

---

## 🔌 Provider 抽象契约

```python
# providers/llm/base.py
class LLMProvider(Protocol):
    async def chat(self, messages: list[Message], stream: bool = False, **kw) -> AsyncIterator[str] | str: ...

# providers/embedding/base.py
class EmbeddingProvider(Protocol):
    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_images(self, images: list[bytes | str]) -> list[list[float]]: ...

# 调用方
from providers import get_llm, get_text_embedder, get_image_embedder
llm = get_llm()
async for chunk in llm.chat(messages, stream=True): ...
```

工厂函数 `get_xxx()` 用 `lru_cache` 缓存,首次调用根据 `settings.xxx.provider` 实例化。切换只改 `.env` 的 provider 字段。

详情见 [`providers/README.md`](providers/README.md)。

### VLM 接入(强烈建议开)

默认 `VISION_PROVIDER=disabled`,陌生图(数据库里没有的图)只能靠 CLIP 视觉相似度匹配 →
经常匹到完全不相关的商品(用户实测发生过,匹到一双 ¥773 的复古靴子)。

**开 VLM 之后**,Agent `IMAGE_UNDERSTAND` 状态会把图片描述成一句中文 caption,
然后这句 caption 喂给 `QUERY_REWRITE` 走文本检索,准确率显著上升。

#### 方案 A:智谱 GLM-4V-Flash(推荐 ✨ 完全免费,步骤最简单)

1. https://open.bigmodel.cn 注册(微信扫码,**不强制实名**)
2. 控制台「API Keys」→ 新建 → 拿 sk-xxx(新用户送 2000 万 Token,Flash 系列**永久免费**)
3. 把以下填进 `backend/.env`:

```bash
VISION_PROVIDER=openai
VISION_API_KEY=<智谱 sk-xxx>
VISION_MODEL=glm-4v-flash
VISION_BASE_URL=https://open.bigmodel.cn/api/paas/v4
```

智谱兼容 OpenAI 协议,走我们已有的 `openai` vision provider,**不用改代码**。

#### 方案 B:火山方舟豆包(免费额度更大,但要实名 + 创建接入点)

1. 注册 https://www.volcengine.com/ → **完成实名认证**(个人/企业都行)
2. 进控制台 → 搜「**火山方舟**」(ark)→ 开通
3. 左侧「**API Key 管理**」→ 新建 → 拿 sk-xxx
4. 左侧「**在线推理 → 推理接入点 → 创建**」:
   - 模型选 `doubao-1.5-vision-pro-32k-250115`
   - 创建后拿到「**接入点 ID**」(`ep-2025xxxxxx-xxxxx`,**不是**模型本名)
5. **手动激活「协作奖励计划」**(控制台右侧活动区)→ 每天 200 万 Token 可循环免费
6. 填 `backend/.env`:

```bash
VISION_PROVIDER=volcengine
VISION_API_KEY=<火山 sk-xxx>
VISION_MODEL=<接入点 ID,如 ep-2025xxxxxx-xxxxx>
VISION_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
```

#### 验证

重启 uvicorn,再发一张图聊天,后端日志会出现:

```
vision.done provider=openai_vision desc_len=42       # 智谱
vision.done provider=volcengine_vision desc_len=42   # 豆包
```

接着 `query_rewrite` 改写后的检索 query 里能看到图片描述的关键词,从此陌生图也走文本路。


---

## 🗂️ HTTP 接口分组(简表)

完整定义看 `http://localhost:8000/docs`。

| 路径 | 用途 |
|---|---|
| `POST /auth/register` / `register/merchant` / `login` / `sms/*` | 注册/登录(public);**管理员不能注册**,只能 `python -m scripts.seed_admin` |
| `GET /auth/me` | 当前用户(带 JWT) |
| `GET /products` | 商品列表 + 筛选 + 分页(public)|
| `GET /products/{id}` / `categories` / `brands` | 商品详情 + 筛选下拉数据 |
| `POST /upload/image` | 上传图片,返回 object_key,后续聊天/商品引用 |
| `POST /chat` (SSE) | 流式聊天,登录用户写库 |
| `GET /chat/sessions` | 当前用户的会话列表(给 /chat 侧栏)|
| `GET /chat/sessions/{id}/messages` | 单段对话的全量消息 |
| `DELETE /chat/sessions/{id}` | 删段对话 |
| `GET /memory` / `DELETE /memory/{id}` / `POST /memory/forget-all` | PIPL 合规面板 |
| `POST /merchant/products` / `GET /merchant/submissions` | 商家入驻提交商品 |
| `GET /admin/submissions` / `POST /admin/submissions/{id}/approve\|reject` | 管理员审核 |
| `GET /static/*` | local_fs storage 模式下的图片直出(自动挂)|

---

## 🧠 两层记忆架构(参考 Mem0 / Letta MemGPT / Zep)

> **这里讲的是 Agent 推理用的"工作内存"。**前端 `/chat` 页左侧栏的历史会话列表
> 走的是 MySQL `sessions` / `messages` 表(归档型,永久保存,见上面 HTTP 接口分组)。
> 两者**互不替代**:Redis STM 给 LLM 看(有 token 阈值 + 滚动摘要),MySQL 归档给用户翻历史。

### 短期记忆(Redis,会话级)
- 实现:`app/core/memory/short_term.py`
- key:`mem:stm:{session_id}:turns|summary|slots|turn_count`
- 最近 `STM_RECENT_TURNS`(默认 8)轮原文保留,超出走滚动摘要
- 总 token 超 `STM_TOKEN_THRESHOLD`(默认 1500)触发摘要重生成
- TTL `STM_TTL_SECONDS`(默认 24h),掉电不可惜,关键事实流到长期层
- 槽位 slots:结构化字段(类目 / 预算 / 品牌),IntentTool 抽出来直接覆盖

### 长期记忆(MySQL + Milvus 双写)
- **MySQL `user_memories`**:`(user_id, fact_type, fact_text, valid_from, valid_to, last_used_at, vector_id, confidence)`
- **双时态**:`valid_to IS NULL` 是当前事实,UPDATE 旧事实置 `valid_to=now()` 而非删,审计可追溯
- **Milvus `user_facts_v1`**:`user_id` 作 `is_partition_key=True`,**硬隔离**,查询只走自己的分区,杜绝串户
- **写入**:对话结束 `extract_user_facts.delay(user_id, [dialog], existing_facts)`,LLM 输出 `FactOp { op: ADD|UPDATE|INVALIDATE|NOOP }`,双时态推进 + 同步 Milvus
- **检索**:`retrieve_facts(user_id, query, top_k=5)` Milvus 召回 + MySQL 过滤 `valid_to IS NULL`,命中后 update `last_used_at`(给 decay 用)
- **衰减**:Celery beat `decay_user_memories` 把 `now - last_used_at > LTM_DECAY_DAYS` 置失效
- **遗忘**:`DELETE /memory/{id}` 和 `POST /memory/forget-all`,PIPL 合规真删

### 关键设计决策
- **不引入新依赖**:复用 BGE-M3 / Milvus / Redis / Celery
- **不无脑注入**:`_INTENTS_NEED_MEMORY = {SEARCH, RECOMMEND, DETAIL, COMPARE}`,闲聊和纯售后跳过
- **不写满上下文**:每次只注入 top-K(`LTM_TOP_K=5`)+ 阈值(`LTM_SCORE_THRESHOLD=0.35`)
- **总开关**:`LTM_ENABLED` 可关掉做对照实验

---

## 🔍 RAG 流水线

### 离线入库(`rag/indexers/`)

1. **父子块切分** Parent / Child Chunking:
   - 父块大(`FATHER_CHUNK_SIZE=800` char)喂 LLM 保上下文
   - 子块小(`CHILD_CHUNK_SIZE=200` char)用于检索保精度
   - 子块带 `parent_id`,Milvus 命中子块后回查父块上下文
2. **图文双路入库**:
   - 文本(标题 + 描述)→ BGE-M3 → `product_text` collection
   - 图片 → Chinese-CLIP → `product_image` collection
   - 两者用同一 `product_id` 关联回 MySQL 主表
3. **幂等去重**:`vector_id = sha256(content + source + model_name + chunk_idx)[:16]`,上库前 `query existing` 跳过
4. **批量入库**(强制走 `rag/indexers/batch.py`):
   - N 个商品所有子块 → 一次 batch embed → 一次 upsert → 末尾才 flush
   - 图像额外做并发拉图(`fetch_concurrency=16`)+ CLIP 一次 forward
   - **实测**:文本 2000 商品 51 秒,图像 1981 张 31 秒(单条版要 5.5 小时,差 100~700×)
   - **严禁退回单条循环**

### 在线 Query 优化(`rag/query_optimizer/`)

按 `.env` 开关,三选一或组合:
- **Rewrite**:上下文消解、口语转检索 query
- **HyDE**:LLM 生成假设回答 → 用其向量去检索
- **MultiQuery**:一个问题展开成 3-5 个角度,各自检索再合并

### 在线检索(`rag/retrievers/`)

1. **多路召回**(每路 top_k 各 20-30):
   - Dense:Milvus 向量召回
   - Sparse:BM25 关键词(`rank-bm25` 内存版)
2. **RRF 融合**:Reciprocal Rank Fusion 多路合并 → 候选 20-30
3. **Rerank 精排**:BGE-Reranker-v2-m3 → 取 top 5(`RERANK_TOP_K=5`)
4. **结构化过滤**:价格 / 类目 / 库存等硬条件在 MySQL 层做

### 阈值过滤(防幻觉)

| 路径 | 阈值 env | 默认 | 含义 |
|---|---|---|---|
| 文本 rerank 后 | `RAG_SCORE_THRESHOLD` | 0.3 | cross-encoder 分数,低于丢 |
| 图像检索后 | `RAG_IMAGE_SCORE_THRESHOLD` | 0.55 | CLIP IP 归一化分,陌生图常 < 0.5,共用 0.3 会误命中 |
| 长期记忆 | `LTM_SCORE_THRESHOLD` | 0.35 | 用户事实相似度 |

低于阈值的候选**不进入 LLM 上下文**。全部被过滤时 Agent 走 `NEED_CLARIFY` 反问或诚实告知"没找到"。

### 输入分流(Agent 层)
- 纯文本 → 文本检索
- 带图片 → 多模态检索(图→图、图→文)
- 纯图片 → 以图搜图 + (若 VLM 启用)图生 caption 走文本路

详情见 [`rag/README.md`](rag/README.md)。

---

## 📋 数据策略

测试数据使用 **MUGE 电商图文检索数据集**(已导入 2000 商品,真实淘宝标题 + 商品图)。

- `scripts/seed_data.py`:读 MUGE jsonl 灌 MySQL,图片下载落 storage
- `scripts/build_index.py`:批量入库走 Milvus(文本 + 图像两路)
- `tests/eval_queries.jsonl`:评估集
- `scripts/eval.py`:跑 Recall@1/5/10/20 / MRR / latency p50/p95
- `scripts/test_image_search.py`:验证图文跨 collection 通过 `product_id` 联通

换数据集(Products-10K / 自爬)只需提供同 schema 的 jsonl。

---

## 📝 日志规约

只打这些(**别打**循环每次 / 每条文档内容 / prompt 全文 / 向量值):

| 时机 | 级别 | 内容 |
|---|---|---|
| API 请求进入 | INFO | method, path, trace_id, user_id |
| API 响应返回 | INFO | status, trace_id, latency_ms |
| Agent 状态切换 | INFO | trace_id, from_state, to_state |
| LLM 调用完成 | INFO | trace_id, model, latency_ms, prompt_tokens, completion_tokens |
| Embedding 调用 | DEBUG | trace_id, count, latency_ms |
| 工具执行 | INFO | trace_id, tool_name, result_summary |
| 检索结果 | INFO | trace_id, recall_count, top_score |
| 异常 | ERROR | trace_id + 完整 traceback |

---

## 📊 关键性能(本地实测)

| 操作 | 数据 | 耗时 |
|------|------|------|
| 文本批量入库 | 2000 商品 → 子块 → BGE-M3 → Milvus | **51 秒** |
| 图像批量入库 | 1981 张图 → CLIP → Milvus | **31 秒** |
| 检索 | dense + sparse + RRF + rerank,top-30/10 | **~ 200ms** |
| 健康探活 | MySQL + Milvus + Redis 并行 | **< 50ms** |

---

## 🧪 测试

```bash
# 全量单测
pytest

# Provider 工厂冒烟(LLM 一发一收 / Embedding 维度 / Rerank 分数)
python -m scripts.test_models

# 图文检索端到端
python -m scripts.test_image_search

# 离线评估
python -m scripts.eval --top-k 10 --concurrent 4 --output report.json
```
