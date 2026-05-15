"""trace_id 中间件 —— 为每个请求生成追踪 ID,贯穿日志和 Agent。"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from agent import new_trace_id


class TraceIDMiddleware(BaseHTTPMiddleware):
    """把 trace_id 注入到 request.state 和响应头,业务代码用 request.state.trace_id。"""

    async def dispatch(self, request: Request, call_next):
        # 允许调用方自带 trace_id(微服务串联场景),否则新生成
        trace_id = request.headers.get("x-trace-id") or new_trace_id()
        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers["x-trace-id"] = trace_id
        return response
