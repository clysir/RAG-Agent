"""Embedding Provider 协议 —— 文本和图像统一接口,实现类按需选择支持哪些方法。"""

from typing import Protocol


class TextEmbeddingProvider(Protocol):
    """纯文本 embedding —— 用于商品标题/描述向量化、用户 query 向量化。"""

    name: str
    model: str
    dim: int  # 向量维度,用于和 Milvus collection schema 校验

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量文本向量化 —— 返回二维 list,每行对应一条输入。"""
        ...


class MultiModalEmbeddingProvider(Protocol):
    """多模态 embedding —— 支持图文映射到同一空间,实现以图搜图、图文跨模态检索。"""

    name: str
    model: str
    dim: int

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...

    async def embed_images(self, images: list[bytes]) -> list[list[float]]:
        """图像向量化 —— 输入为图片二进制(jpeg/png 字节流)。"""
        ...
