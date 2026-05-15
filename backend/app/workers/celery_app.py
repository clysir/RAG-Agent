"""Celery 应用 —— Redis 作为 broker 和 backend。

启动 worker:
    celery -A app.workers.celery_app worker -l info -Q default
    # dev 模式可加 --concurrency=2 减资源
"""

from celery import Celery

from config import settings

celery_app = Celery(
    "rag_agent",
    broker=settings.redis.celery_url,
    backend=settings.redis.celery_url,
    # 任务模块自动发现,放在 tasks 子模块
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # 时区固定 UTC,避免和业务时区耦合
    timezone="UTC",
    enable_utc=True,
    # 限制单任务最长执行时间,防卡死
    task_time_limit=settings.celery.task_time_limit,
    # 预取调小,避免长任务把短任务阻塞在队列里
    worker_prefetch_multiplier=1,
    # 任务完成才 ack,worker 挂掉时 Redis 会重发
    task_acks_late=True,
    # 默认队列
    task_default_queue=settings.celery.default_queue,
    worker_concurrency=settings.celery.worker_concurrency,
)
