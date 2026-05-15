"""MinIO 实现 —— S3 兼容,本地 docker-compose 已经预置 MinIO 服务。

注意:
- minio Python SDK 是同步的,所有 IO 操作丢线程池
- bucket 不存在时启动期自动创建,避免运行时报错
- presign_url 返回带签名的 HTTP URL,默认 1 小时过期
"""

import asyncio
from io import BytesIO

from loguru import logger
from minio import Minio
from minio.error import S3Error

from app.core import with_latency
from config import settings
from providers.storage.base import StorageProvider


class MinioStorage(StorageProvider):
    """MinIO Provider —— S3 兼容 API。"""

    name = "minio"

    def __init__(self) -> None:
        cfg = settings.storage
        self._bucket = cfg.bucket
        self._presign_ttl = cfg.presign_ttl
        self._client = Minio(
            cfg.endpoint,
            access_key=cfg.access_key.get_secret_value(),
            secret_key=cfg.secret_key.get_secret_value(),
            secure=cfg.secure,
            region=cfg.region,
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        """启动期保证 bucket 存在,失败抛错让 lifespan 捕获。"""
        try:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
                logger.info(f"storage.bucket_created name={self._bucket}")
        except S3Error as e:
            # bucket 已存在的 race condition 是良性的
            if e.code != "BucketAlreadyOwnedByYou":
                raise

    @with_latency("storage.minio.put")
    async def put(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> str:
        def _put():
            self._client.put_object(
                self._bucket,
                key,
                BytesIO(data),
                length=len(data),
                content_type=content_type,
            )

        await asyncio.to_thread(_put)
        return key

    @with_latency("storage.minio.get")
    async def get(self, key: str) -> bytes:
        def _get():
            try:
                resp = self._client.get_object(self._bucket, key)
                try:
                    return resp.read()
                finally:
                    resp.close()
                    resp.release_conn()
            except S3Error as e:
                if e.code in ("NoSuchKey", "NoSuchObject"):
                    raise FileNotFoundError(key) from e
                raise

        return await asyncio.to_thread(_get)

    async def delete(self, key: str) -> None:
        def _del():
            try:
                self._client.remove_object(self._bucket, key)
            except S3Error as e:
                if e.code not in ("NoSuchKey", "NoSuchObject"):
                    raise

        await asyncio.to_thread(_del)

    async def presign_url(self, key: str, ttl_seconds: int | None = None) -> str:
        from datetime import timedelta

        ttl = timedelta(seconds=ttl_seconds or self._presign_ttl)
        return await asyncio.to_thread(
            self._client.presigned_get_object, self._bucket, key, expires=ttl
        )

    async def exists(self, key: str) -> bool:
        def _stat():
            try:
                self._client.stat_object(self._bucket, key)
                return True
            except S3Error as e:
                if e.code in ("NoSuchKey", "NoSuchObject"):
                    return False
                raise

        return await asyncio.to_thread(_stat)
