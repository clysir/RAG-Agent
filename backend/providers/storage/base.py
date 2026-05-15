"""存储 Provider 协议 —— 业务代码只依赖这个接口。

为什么:
- 用户上传图片 / 商家上传商品图 / 用户上传 PDF 都走存储层
- 切换 MinIO -> S3 -> OSS 只改 .env,代码零改动
- 业务表存 object_key,展示通过 presign_url 拿临时 URL
"""

from typing import Protocol


class StorageProvider(Protocol):
    """对象存储统一接口。

    object_key 是存储里的逻辑路径,例如 "uploads/user_123/abc.jpg"。
    业务表持久化它,而不是 URL —— URL 可能因为 presign 过期、bucket 改名而失效。
    """

    name: str

    async def put(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> str:
        """写入对象 —— 返回 object_key。已存在则覆盖。"""
        ...

    async def get(self, key: str) -> bytes:
        """读取对象 —— 不存在抛 FileNotFoundError。"""
        ...

    async def delete(self, key: str) -> None:
        """删除对象 —— 不存在静默通过。"""
        ...

    async def presign_url(self, key: str, ttl_seconds: int | None = None) -> str:
        """生成临时访问 URL —— 前端展示用,过期后失效。"""
        ...

    async def exists(self, key: str) -> bool:
        """判断对象是否存在。"""
        ...
