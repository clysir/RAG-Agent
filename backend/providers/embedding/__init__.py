"""Embedding Provider 子包 —— 对外暴露工厂和协议。"""

from providers.embedding.base import MultiModalEmbeddingProvider, TextEmbeddingProvider
from providers.embedding.factory import get_image_embedder, get_text_embedder

__all__ = [
    "TextEmbeddingProvider",
    "MultiModalEmbeddingProvider",
    "get_text_embedder",
    "get_image_embedder",
]
