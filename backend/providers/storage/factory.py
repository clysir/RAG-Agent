"""存储工厂 —— 按 settings.storage.provider 选实现。"""

from functools import lru_cache

from config import settings
from providers.storage.base import StorageProvider


@lru_cache
def get_storage() -> StorageProvider:
    """存储 provider 单例。"""
    provider = settings.storage.provider
    if provider == "minio":
        from providers.storage.minio_impl import MinioStorage

        return MinioStorage()
    if provider == "local_fs":
        from providers.storage.local_fs import LocalFSStorage

        return LocalFSStorage()
    if provider == "s3":
        # aioboto3 原生异步 + SigV4 + IAM Role 支持,
        # endpoint_url 留空走 AWS 公有云,填则走阿里 OSS / 腾讯 COS / 华为 OBS / R2 等 S3 兼容服务
        from providers.storage.s3 import S3Storage

        return S3Storage()
    raise ValueError(f"未知 storage provider: {provider}")
