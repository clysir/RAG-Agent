"""AWS S3 / S3 兼容存储 Provider —— 用 aioboto3 走原生异步 SigV4。

为什么不复用 MinIO 实现:
- AWS S3 + IAM Role / STS 临时凭证只 boto3 / aiobotocore 支持
- aioboto3 是原生 async,不像 minio SDK 是同步 + to_thread
- 多段上传(>5MB 自动 multipart)由 SDK 处理,生产级别
- 同样支持阿里云 OSS / 腾讯云 COS / 华为云 OBS / Cloudflare R2 等 S3 兼容服务,
  endpoint_url + region 切换即可

凭证来源(按 boto3 标准优先级):
1. settings.storage.access_key / secret_key(显式)
2. 环境变量 AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
3. ~/.aws/credentials profile
4. EC2 IAM Role / EKS IRSA / ECS Task Role(生产推荐)
"""

from datetime import timedelta

import aioboto3
from botocore.exceptions import ClientError
from loguru import logger

from app.core import with_latency
from config import settings
from providers.storage.base import StorageProvider


class S3Storage(StorageProvider):
    """AWS S3 / S3 兼容 Provider。"""

    name = "s3"

    def __init__(self) -> None:
        cfg = settings.storage
        self._bucket = cfg.bucket
        self._presign_ttl = cfg.presign_ttl
        self._region = cfg.region
        # endpoint_url 为空时走 AWS 公有云;否则走 S3 兼容端点(阿里 OSS / 腾讯 COS 等)
        endpoint = cfg.endpoint.strip()
        self._endpoint_url: str | None = None
        if endpoint:
            self._endpoint_url = endpoint if endpoint.startswith("http") else (
                f"https://{endpoint}" if cfg.secure else f"http://{endpoint}"
            )

        # 显式凭证可空 —— 让 boto3 fallback 到环境变量 / IAM Role
        ak = cfg.access_key.get_secret_value() or None
        sk = cfg.secret_key.get_secret_value() or None
        self._session = aioboto3.Session(
            aws_access_key_id=ak,
            aws_secret_access_key=sk,
            region_name=self._region,
        )
        # 启动时尝试创建 bucket(幂等)
        self._bucket_ensured = False

    def _client_kwargs(self) -> dict:
        kw = {"service_name": "s3"}
        if self._endpoint_url:
            kw["endpoint_url"] = self._endpoint_url
        return kw

    async def _ensure_bucket(self) -> None:
        if self._bucket_ensured:
            return
        async with self._session.client(**self._client_kwargs()) as s3:
            try:
                await s3.head_bucket(Bucket=self._bucket)
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code in ("404", "NoSuchBucket"):
                    create_kw: dict = {"Bucket": self._bucket}
                    # us-east-1 不需要 LocationConstraint,其它 region 必须带
                    if self._region and self._region != "us-east-1":
                        create_kw["CreateBucketConfiguration"] = {
                            "LocationConstraint": self._region
                        }
                    await s3.create_bucket(**create_kw)
                    logger.info(f"storage.s3.bucket_created name={self._bucket}")
                elif code != "BucketAlreadyOwnedByYou":
                    raise
        self._bucket_ensured = True

    @with_latency("storage.s3.put")
    async def put(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> str:
        await self._ensure_bucket()
        async with self._session.client(**self._client_kwargs()) as s3:
            await s3.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )
        return key

    @with_latency("storage.s3.get")
    async def get(self, key: str) -> bytes:
        async with self._session.client(**self._client_kwargs()) as s3:
            try:
                resp = await s3.get_object(Bucket=self._bucket, Key=key)
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code in ("NoSuchKey", "404"):
                    raise FileNotFoundError(key) from e
                raise
            body = await resp["Body"].read()
            return body

    async def delete(self, key: str) -> None:
        async with self._session.client(**self._client_kwargs()) as s3:
            try:
                await s3.delete_object(Bucket=self._bucket, Key=key)
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code not in ("NoSuchKey", "404"):
                    raise

    async def presign_url(self, key: str, ttl_seconds: int | None = None) -> str:
        ttl = ttl_seconds or self._presign_ttl
        async with self._session.client(**self._client_kwargs()) as s3:
            return await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=int(ttl),
            )

    async def exists(self, key: str) -> bool:
        async with self._session.client(**self._client_kwargs()) as s3:
            try:
                await s3.head_object(Bucket=self._bucket, Key=key)
                return True
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code in ("NoSuchKey", "404"):
                    return False
                raise
