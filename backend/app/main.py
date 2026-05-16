"""FastAPI 应用入口 —— 启动命令: `python -m app --dev` 或 `uvicorn app.main:app`。

注意: 用 `python -m app` 启动可解析 --dev/--op,直接 uvicorn 走 .env 配置。
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.api import api_router
from app.core import setup_logging
from app.middleware import RequestLogMiddleware, TraceIDMiddleware
from config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期 —— 启动时初始化日志和向量库,关闭时释放资源。"""
    setup_logging()
    logger.info(f"app.starting mode={settings.app_mode}")

    try:
        from rag import ensure_collections

        ensure_collections()
    except Exception as e:
        logger.warning(f"app.milvus_init_failed reason={e}")

    yield

    logger.info("app.shutdown")


app = FastAPI(
    title="RAG-Agent",
    description="多模态电商智能导购 Agent",
    version="0.1.0",
    lifespan=lifespan,
    # op 模式隐藏 OpenAPI 文档以减小攻击面
    docs_url="/docs" if settings.is_dev else None,
    redoc_url="/redoc" if settings.is_dev else None,
    openapi_url="/openapi.json" if settings.is_dev else None,
)

# 中间件顺序: trace 在最外层,这样所有其它中间件都能读到 trace_id
app.add_middleware(RequestLogMiddleware)
app.add_middleware(TraceIDMiddleware)

# dev 模式 CORS 全开,op 模式收紧(需在 .env 显式配置允许域名)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_dev else [],
    allow_credentials=True,
    allow_methods=["*"] if settings.is_dev else ["GET", "POST"],
    allow_headers=["*"],
    expose_headers=["x-trace-id"],
)

app.include_router(api_router)

# local_fs 存储下 presign_url 返回 "/static/{key}",需要这里挂静态目录把图片暴露出来。
# minio / s3 自带 HTTP 服务,不走这里。
if settings.storage.provider == "local_fs":
    static_root = Path(settings.storage.local_root).resolve()
    static_root.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_root)), name="static")
    logger.info(f"app.static_mounted path=/static root={static_root}")
