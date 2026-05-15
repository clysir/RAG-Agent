"""本地文件系统 Provider —— 极简,适合无网络/CI 测试。

presign_url 没有真实签名能力,直接返回相对路径,需要业务上挂一个静态文件服务。
"""

import asyncio
from pathlib import Path

from app.core import with_latency
from config import settings
from providers.storage.base import StorageProvider


class LocalFSStorage(StorageProvider):
    """本地存储 —— 把对象当文件存到 storage.local_root。"""

    name = "local_fs"

    def __init__(self) -> None:
        self._root = Path(settings.storage.local_root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # 防 path traversal:strip 开头的 / 然后 resolve 校验
        safe = key.lstrip("/").replace("..", "_")
        full = (self._root / safe).resolve()
        if not str(full).startswith(str(self._root)):
            raise ValueError(f"unsafe key: {key}")
        return full

    @with_latency("storage.local.put")
    async def put(self, key: str, data: bytes, content_type: str = "") -> str:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(p.write_bytes, data)
        return key

    async def get(self, key: str) -> bytes:
        p = self._path(key)
        if not p.exists():
            raise FileNotFoundError(key)
        return await asyncio.to_thread(p.read_bytes)

    async def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            await asyncio.to_thread(p.unlink)

    async def presign_url(self, key: str, ttl_seconds: int | None = None) -> str:
        # 本地实现没有签名,业务上需要单独挂静态文件路由 /static/{key}
        return f"/static/{key.lstrip('/')}"

    async def exists(self, key: str) -> bool:
        return self._path(key).exists()
