"""模型加载与推理冒烟测试 —— 跑这个会触发首次下载(~5GB)。

运行: HF_ENDPOINT=https://hf-mirror.com .venv/bin/python -m scripts.test_models

会依次验证:
1. BGE-M3 文本 embedding
2. chinese-CLIP 文本 + 图像 embedding(检查文本/图像向量在同一空间)
3. bge-reranker-v2-m3 精排打分
"""

import asyncio
import io
import os
import time

# 确保 HF 镜像在 import 任何 hub 客户端之前生效;
# 注意:实际配置由 config.settings 自动注入,这里再设一遍保险(直接跑此脚本时)
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

from loguru import logger


async def test_bge_m3():
    logger.info("=== 1. BGE-M3 文本 embedding ===")
    from providers.embedding.local_bge import LocalBGEEmbedding

    embedder = LocalBGEEmbedding()
    t0 = time.perf_counter()
    vecs = await embedder.embed_texts(
        ["女款通勤双肩包,500 元以内,百搭风格", "羊毛大衣 冬季 显瘦"]
    )
    dt = (time.perf_counter() - t0) * 1000
    logger.info(f"BGE-M3 OK: {len(vecs)} vectors, dim={len(vecs[0])}, elapsed={dt:.0f}ms")
    return vecs


async def test_chinese_clip():
    logger.info("=== 2. chinese-CLIP 多模态 embedding ===")
    from providers.embedding.local_clip import LocalChineseCLIP

    clip = LocalChineseCLIP()

    # 文本
    t0 = time.perf_counter()
    text_vecs = await clip.embed_texts(["一只可爱的橘色猫", "黑色帆布双肩包"])
    dt_t = (time.perf_counter() - t0) * 1000
    logger.info(f"CLIP text OK: {len(text_vecs)} vectors, dim={len(text_vecs[0])}, elapsed={dt_t:.0f}ms")

    # 图像 —— 用 PIL 造一张纯色图代替真实图片,主要验证管线
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (224, 224), color=(255, 128, 0)).save(buf, format="JPEG")
    img_bytes = buf.getvalue()

    t0 = time.perf_counter()
    img_vecs = await clip.embed_images([img_bytes])
    dt_i = (time.perf_counter() - t0) * 1000
    logger.info(f"CLIP image OK: dim={len(img_vecs[0])}, elapsed={dt_i:.0f}ms")

    # 校验:文本和图像向量维度一致 + 已 L2 归一化(norm ≈ 1)
    import math

    norm = math.sqrt(sum(x * x for x in text_vecs[0]))
    logger.info(f"text norm = {norm:.4f}  (应该接近 1.0)")


async def test_reranker():
    logger.info("=== 3. bge-reranker-v2-m3 精排 ===")
    from providers.rerank.local_bge import LocalBGERerank

    reranker = LocalBGERerank()
    query = "适合通勤的双肩包"
    candidates = [
        "黑色商务双肩包,15 寸笔记本,防泼水,百搭通勤",
        "户外登山背包,60L 容量,适合长途徒步",
        "可爱卡通儿童书包,适合 6-10 岁",
        "真皮女士手提包,小众设计师品牌",
    ]
    t0 = time.perf_counter()
    ranked = await reranker.rerank(query, candidates, top_k=4)
    dt = (time.perf_counter() - t0) * 1000
    logger.info(f"reranker elapsed={dt:.0f}ms")
    for idx, score in ranked:
        logger.info(f"  {score:.3f}  {candidates[idx]}")


async def main():
    import torch

    logger.info(f"torch.cuda.is_available()={torch.cuda.is_available()}")
    if torch.cuda.is_available():
        logger.info(f"GPU={torch.cuda.get_device_name(0)}")

    await test_bge_m3()
    await test_chinese_clip()
    await test_reranker()
    logger.info("=== 全部完成 ===")


if __name__ == "__main__":
    asyncio.run(main())
