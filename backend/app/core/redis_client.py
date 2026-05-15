"""Redis 异步客户端单例 —— 业务代码用 get_redis() 拿连接池。

用例:
- 短信验证码存取(TTL 5 分钟)
- 频率限制(发码间隔、每日上限)
- 短期会话记忆(后续 Agent 上下文缓存)
- 语义缓存(后续可加)
"""

from functools import lru_cache

import redis.asyncio as redis_async

from config import settings


@lru_cache
def get_redis() -> redis_async.Redis:
    """返回异步 Redis 客户端单例 —— 进程内复用连接池。"""
    return redis_async.Redis(
        host=settings.redis.host,
        port=settings.redis.port,
        db=settings.redis.db,
        decode_responses=True,  # 返回 str 而非 bytes,便于业务使用
        socket_keepalive=True,
    )
