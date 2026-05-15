"""核心子包 —— 启动、日志、依赖注入、横切关注点等共享设施。"""

from app.core.logging import setup_logging
from app.core.mode import with_latency
from app.core.redis_client import get_redis

__all__ = ["setup_logging", "with_latency", "get_redis"]

