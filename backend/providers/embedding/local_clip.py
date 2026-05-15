"""本地 chinese-CLIP 多模态 Embedding —— 走 transformers,模型 OFA-Sys/chinese-clip-vit-base-patch16。

设计:
- 同一个模型同时支持文本和图像 encoding,产出 512 维向量,二者在同一向量空间
- 文本走 encode_text,图像走 encode_image,业务侧两边各调一边即可
- fp16 + GPU 优先,无 GPU 自动回退 CPU
- transformers 同步 API,推理走 asyncio.to_thread

为什么不用 cn_clip 官方包:
- 多一层依赖,而且和 transformers 的 ChineseCLIPModel 等价(后者还省了 cn_clip 的额外 weights 下载)
"""

import asyncio
import io

from loguru import logger

from app.core import with_latency
from config import settings
from providers.embedding.base import MultiModalEmbeddingProvider


class LocalChineseCLIP(MultiModalEmbeddingProvider):
    """chinese-CLIP base —— 512 维多模态向量。"""

    name = "local_clip"

    def __init__(self) -> None:
        self.model = settings.mm_embedding.model
        self.dim = settings.milvus.image_dim
        self._model = None
        self._processor = None
        self._device = None

    def _lazy_load(self):
        """惰性加载 —— 进程内单例,首次调用才下载 + 装显存。"""
        if self._model is not None:
            return
        import torch
        from transformers import ChineseCLIPModel, ChineseCLIPProcessor

        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        # fp16 在 GPU 上省显存且更快,CPU 上保留 fp32 避免精度问题
        dtype = torch.float16 if self._device == "cuda" else torch.float32

        logger.info(f"clip.loading model={self.model} device={self._device} dtype={dtype}")
        self._model = ChineseCLIPModel.from_pretrained(self.model, torch_dtype=dtype).to(
            self._device
        )
        self._model.eval()
        self._processor = ChineseCLIPProcessor.from_pretrained(self.model)

    @with_latency("embedding.clip.text")
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        await asyncio.to_thread(self._lazy_load)
        return await asyncio.to_thread(self._embed_texts_sync, texts)

    def _embed_texts_sync(self, texts: list[str]) -> list[list[float]]:
        import torch

        inputs = self._processor(text=texts, padding=True, return_tensors="pt").to(self._device)
        with torch.no_grad():
            # transformers 4.57 的 ChineseCLIPModel.get_text_features 在某些版本下
            # pooler_output 会返回 None,这里手动走 text_model 取 last_hidden_state
            # 再做 mean pooling,再过 text_projection,效果等价。
            text_outputs = self._model.text_model(
                input_ids=inputs["input_ids"],
                attention_mask=inputs.get("attention_mask"),
                token_type_ids=inputs.get("token_type_ids"),
            )
            # 取 [CLS] 位置的 hidden state(等价于 pooler_output 在没 pooler 时的回退)
            pooled = text_outputs.last_hidden_state[:, 0, :]
            feats = self._model.text_projection(pooled)
        # L2 归一化,Milvus 用 IP 度量等价余弦相似度
        feats = feats / feats.norm(p=2, dim=-1, keepdim=True)
        return feats.cpu().float().tolist()

    @with_latency("embedding.clip.image")
    async def embed_images(self, images: list[bytes]) -> list[list[float]]:
        if not images:
            return []
        await asyncio.to_thread(self._lazy_load)
        return await asyncio.to_thread(self._embed_images_sync, images)

    def _embed_images_sync(self, images: list[bytes]) -> list[list[float]]:
        import torch
        from PIL import Image

        pil_images = [Image.open(io.BytesIO(b)).convert("RGB") for b in images]
        inputs = self._processor(images=pil_images, return_tensors="pt").to(self._device)
        with torch.no_grad():
            # 同样手动走 vision_model 避免 pooler_output 为 None 的兼容问题
            vision_outputs = self._model.vision_model(pixel_values=inputs["pixel_values"])
            pooled = vision_outputs.last_hidden_state[:, 0, :]
            feats = self._model.visual_projection(pooled)
        feats = feats / feats.norm(p=2, dim=-1, keepdim=True)
        return feats.cpu().float().tolist()
