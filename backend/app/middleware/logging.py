"""请求日志中间件 —— 只打进入/退出两条,符合 CLAUDE.md 的日志规范。"""

import time

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = getattr(request.state, "trace_id", "-")
        start = time.perf_counter()
        logger.info(f"http.in trace_id={trace_id} {request.method} {request.url.path}")
        try:
            response = await call_next(request)
        except Exception:
            elapsed = (time.perf_counter() - start) * 1000
            logger.exception(f"http.error trace_id={trace_id} elapsed_ms={elapsed:.1f}")
            raise
        elapsed = (time.perf_counter() - start) * 1000
        logger.info(
            f"http.out trace_id={trace_id} status={response.status_code} elapsed_ms={elapsed:.1f}"
        )
        return response
