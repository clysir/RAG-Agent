"""Embedding 工厂 —— 文本和多模态两条线,各自独立选 provider。"""

from functools import lru_cache

from config import settings
from providers.embedding.base import MultiModalEmbeddingProvider, TextEmbeddingProvider


@lru_cache
def get_text_embedder() -> TextEmbeddingProvider:
    """文本 embedding 单例。"""
    provider = settings.embedding.provider

    if provider == "local_bge":
        from providers.embedding.local_bge import LocalBGEEmbedding

        return LocalBGEEmbedding()

    if provider == "volcengine":
        raise NotImplementedError("volcengine 文本 embedding 尚未实现")
    if provider == "openai":
        raise NotImplementedError("openai 文本 embedding 尚未实现")

    raise ValueError(f"未知 embedding provider: {provider}")


@lru_cache
def get_image_embedder() -> MultiModalEmbeddingProvider:
    """多模态 embedding 单例 —— 同时支持文本和图像编码到同一空间。"""
    provider = settings.mm_embedding.provider

    if provider == "local_clip":
        from providers.embedding.local_clip import LocalChineseCLIP

        return LocalChineseCLIP()
    if provider == "volcengine":
        raise NotImplementedError("volcengine 多模态 embedding 尚未实现")

    raise ValueError(f"未知多模态 embedding provider: {provider}")
