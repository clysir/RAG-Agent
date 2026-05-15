# RAG-Agent

> **多模态电商智能导购 Agent**

工程级 RAG 系统:用户用自然语言或图片提问,Agent 自动调用文本 + 多模态混合检索 + 跨模态精排,在 2000+ MUGE 电商 SKU 上给出带引用的推荐回答,全程 SSE 流式输出。前端用 Next.js + shadcn/ui 提供商品浏览 + 悬浮聊天 + 完整聊天页。

---

## 📂 仓库结构

```
rag-agent/
├── CLAUDE.md          强制规范(技术栈锁定 + 不可违反的规则)
├── .gitignore         统一忽略(覆盖 backend + frontend)
├── backend/           Python / FastAPI / RAG / Agent / Celery / docker-compose
│   └── README.md      → 后端完整架构 + 跑法 + 模块文档索引
└── frontend/          Next.js 15 + shadcn/ui + Zustand + TanStack Query
    └── README.md      → 前端架构 + 跑法 + 组件结构
```

各子目录有详细 README,**不要在本文件复述**。

---

## ✨ 核心能力

| 能力 | 实现 |
|------|------|
| **自研状态机 Agent** | 8 状态显式编排,无 LangGraph / LangChain |
| **多模态混合检索** | BGE-M3 文本向量 + Chinese-CLIP 图像向量,通过 `product_id` 联通 |
| **多路召回 + RRF 融合** | Dense (Milvus) + Sparse (BM25) → RRF → cross-encoder rerank → 阈值过滤 |
| **两层记忆** | Redis 滑动窗口(短期) + MySQL + Milvus 双时态事实库(长期,Mem0 风格) |
| **Provider 抽象** | LLM / Embedding / Rerank / Vision / Storage / SMS 全协议化,切换改 `.env` |
| **dev / op 双模式** | `--dev` / `--op` CLI 覆盖,横切日志 / SQL echo / latency / CORS |
| **批量入库** | 一次 embed + 一次 upsert + 末尾 flush,2000 商品 51 秒(单条快 100×) |
| **防幻觉** | rerank 阈值过滤 + 召回为空时反问澄清,**不基于低分候选编造** |
| **流式 SSE** | `state_change` + `tool_output` + `token` + `done` 事件 |
| **前端悬浮聊天** | 商品浏览页右下角气泡 → 展开面板,与完整 `/chat` 页共享同一 session |

---

## 🏗️ 高层架构

```
┌──────────────────────────────────────────────────────────────┐
│  Next.js 前端                                                │
│  - 商品网格 + 详情(GET /products)                            │
│  - 完整聊天页 /chat + 悬浮气泡(POST /chat SSE)               │
│  - 认证 / 我的记忆 / 商家提交 / 管理员审核                    │
└──────────────────────┬───────────────────────────────────────┘
                       │ HTTPS + SSE
┌──────────────────────▼───────────────────────────────────────┐
│  FastAPI 后端 (app/)                                         │
│  middleware: trace_id / logging / CORS                       │
│  routers: /chat /auth /products /upload /memory /merchant ...│
└──────────────────────┬───────────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  Agent 状态机 (agent/)                                       │
│  INTENT → LOAD_MEMORY → IMAGE_UNDERSTAND → QUERY_REWRITE →   │
│  RETRIEVE(Dense + Sparse + RRF)→                            │
│  RERANK(cross-encoder + 阈值)→ NEED_CLARIFY | RESPOND → END  │
└──────────────────────┬───────────────────────────────────────┘
                       │
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐
│ rag/         │ │ providers/   │ │ db/ + config/        │
│ retrievers   │ │ llm / embed  │ │ MySQL ORM + Settings │
│ indexers     │ │ rerank/vision│ │ Alembic 迁移         │
│ query_opt    │ │ storage/sms  │ │ _SubSettings 基类    │
└──────┬───────┘ └──────┬───────┘ └──────────────────────┘
       │                │
       ▼                ▼
┌──────────────────────────────────────────────────────────────┐
│  基础设施:MySQL 8 / Milvus 2.4 / Redis / MinIO / Celery     │
└──────────────────────────────────────────────────────────────┘
```

依赖方向**单向**:`app → agent → rag/providers → db/config`。反向 import 在 review 阶段一票否决。

---

## 🚀 快速开始

完整步骤见各子目录 README。最短启动:

```bash
# 后端
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[embedding-local]"
docker compose -f docker/docker-compose.yml up -d
cp .env.example .env  # 填 LLM_API_KEY
alembic upgrade head
python -m scripts.download_models
python -m scripts.seed_data
python -m scripts.build_index
uvicorn app.main:app --reload --port 8000

# 前端(另开一个终端)
cd frontend
pnpm install
pnpm dev   # 起在 http://localhost:3000
```

---

## 📊 关键性能(本地实测)

| 操作 | 数据规模 | 耗时 |
|------|---------|------|
| 文本批量入库 | 2000 商品 → 子块 → BGE-M3 → Milvus | **51 秒** |
| 图像批量入库 | 1981 张图 → CLIP → Milvus | **31 秒** |
| 检索(dense + sparse + RRF + rerank) | top-30 召回 + top-10 精排 | **~ 200ms** |
| 健康探活 | MySQL + Milvus + Redis 并行 | < 50ms |




