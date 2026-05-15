"""本地 BGE 文本 Embedding —— 通过 FlagEmbedding 加载 bge-m3,无需 API key。

注意:
- 首次加载会从 HuggingFace 下载模型(约 2GB),后续走本地缓存
- 模型加载较重,工厂用 lru_cache 保证单例
- 实际推理是同步的,这里用 asyncio.to_thread 包到协程上下文
"""

import asyncio

from config import settings
from providers.embedding.base import TextEmbeddingProvider


class LocalBGEEmbedding(TextEmbeddingProvider):
    """本地 BGE-M3 实现 —— 1024 维稠密向量,中英双语强。"""

    name = "local_bge"

    def __init__(self) -> None:
        self.model = settings.embedding.model
        self.dim = settings.milvus.text_dim
        # 延迟到首次调用时再加载模型,避免启动慢
        self._encoder = None

    def _lazy_load(self):
        """惰性加载 —— 进程内只加载一次。"""
        if self._encoder is None:
            # 这里 import 是为了让没装 embedding-local 依赖的环境也能 import 本模块
            from FlagEmbedding import BGEM3FlagModel

            # use_fp16=True 降显存,CPU 上自动忽略
            self._encoder = BGEM3FlagModel(self.model, use_fp16=True)
        return self._encoder

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        encoder = self._lazy_load()
        # FlagEmbedding 是同步 API,丢到线程池避免阻塞事件循环
        result = await asyncio.to_thread(
            encoder.encode, texts, batch_size=32, max_length=512
        )
        # BGE-M3 返回 dict,取 dense_vecs 字段
        return result["dense_vecs"].tolist()
