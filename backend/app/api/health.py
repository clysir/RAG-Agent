"""健康检查端点 —— 并发探测 MySQL / Milvus / Redis,dev 模式给详细错误信息。

设计:
- 并发跑三路探针,避免串行累积超时
- 单路超时默认 2 秒,防一个挂的依赖拖垮整个 health 接口
- dev 模式返完整 detail 给排查;op 模式只返 ok/detail 简短状态
- 返回 200 即便依赖 down —— Kubernetes 等编排系统该看 data 字段判断,
  不需要 HTTP 状态码翻转
"""

import asyncio
import time

from fastapi import APIRouter
from loguru import logger
from sqlalchemy import text as sa_text

from app.core.redis_client import get_redis
from config import settings
from db import SessionLocal
from schemas import DependencyStatus, Envelope, HealthData

router = APIRouter()

# 单路探针超时(秒) —— 防止某个挂掉的依赖拖死 /health
_PROBE_TIMEOUT = 2.0


async def _probe_mysql() -> DependencyStatus:
    """MySQL: SELECT 1。"""
    t0 = time.perf_counter()
    try:
        async with SessionLocal() as session:
            await asyncio.wait_for(
                session.execute(sa_text("SELECT 1")), timeout=_PROBE_TIMEOUT
            )
        return DependencyStatus(ok=True, latency_ms=(time.perf_counter() - t0) * 1000)
    except Exception as e:  # noqa: BLE001
        return DependencyStatus(
            ok=False,
            latency_ms=(time.perf_counter() - t0) * 1000,
            detail=str(e) if settings.is_dev else "mysql_down",
        )


async def _probe_redis() -> DependencyStatus:
    """Redis: PING。"""
    t0 = time.perf_counter()
    try:
        r = get_redis()
        pong = await asyncio.wait_for(r.ping(), timeout=_PROBE_TIMEOUT)
        if not pong:
            raise RuntimeError("ping returned falsy")
        return DependencyStatus(ok=True, latency_ms=(time.perf_counter() - t0) * 1000)
    except Exception as e:  # noqa: BLE001
        return DependencyStatus(
            ok=False,
            latency_ms=(time.perf_counter() - t0) * 1000,
            detail=str(e) if settings.is_dev else "redis_down",
        )


async def _probe_milvus() -> DependencyStatus:
    """Milvus: 列 collection(连接 + 元数据查询同时验证)。"""
    t0 = time.perf_counter()
    try:
        from pymilvus import utility

        from rag.milvus_client import _connect

        def _sync_probe() -> list[str]:
            _connect()
            return utility.list_collections()

        await asyncio.wait_for(asyncio.to_thread(_sync_probe), timeout=_PROBE_TIMEOUT)
        return DependencyStatus(ok=True, latency_ms=(time.perf_counter() - t0) * 1000)
    except Exception as e:  # noqa: BLE001
        return DependencyStatus(
            ok=False,
            latency_ms=(time.perf_counter() - t0) * 1000,
            detail=str(e) if settings.is_dev else "milvus_down",
        )


@router.get("/health", response_model=Envelope[HealthData])
async def health() -> Envelope[HealthData]:
    """并发探测三大依赖,返回综合状态。"""
    mysql_st, milvus_st, redis_st = await asyncio.gather(
        _probe_mysql(), _probe_milvus(), _probe_redis()
    )

    # 综合状态:mysql down → down;其它 down → degraded;全 ok → ok
    if not mysql_st.ok:
        status = "down"
    elif not (milvus_st.ok and redis_st.ok):
        status = "degraded"
    else:
        status = "ok"

    if status != "ok":
        logger.warning(
            f"health.degraded mysql={mysql_st.ok} milvus={milvus_st.ok} redis={redis_st.ok}"
        )

    return Envelope[HealthData](
        data=HealthData(
            status=status,
            mode=settings.app_mode,
            mysql=mysql_st,
            milvus=milvus_st,
            redis=redis_st,
        )
    )
