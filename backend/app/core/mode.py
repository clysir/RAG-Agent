"""模式相关基础设施 —— latency 装饰器、模式判断、调试辅助。

设计:
- @with_latency 同时支持 async 和 sync 函数
- dev 模式下输出 module.action elapsed_ms;op 模式下静默(可拓展到 metrics)
- 业务代码不需要 if dev/op 判断,统一加装饰器即可
"""

import functools
import time
from typing import Any, Awaitable, Callable, TypeVar

from loguru import logger

from config import settings

F = TypeVar("F", bound=Callable[..., Any])


def with_latency(label: str) -> Callable[[F], F]:
    """记录函数耗时 —— dev 模式打日志,op 模式静默。

    用法:
        @with_latency("rag.hybrid_search")
        async def hybrid_search(...): ...
    """

    def decorator(func: F) -> F:
        if _is_coroutine(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                if not settings.latency_log_enabled:
                    return await func(*args, **kwargs)
                start = time.perf_counter()
                try:
                    return await func(*args, **kwargs)
                finally:
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    logger.debug(f"latency {label} elapsed_ms={elapsed_ms:.1f}")

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            if not settings.latency_log_enabled:
                return func(*args, **kwargs)
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                logger.debug(f"latency {label} elapsed_ms={elapsed_ms:.1f}")

        return sync_wrapper  # type: ignore[return-value]

    return decorator


def _is_coroutine(func: Callable) -> bool:
    """判断是否协程函数 —— 区分装饰策略。"""
    import inspect

    return inspect.iscoroutinefunction(func)
