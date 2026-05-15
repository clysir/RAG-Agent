"""视觉理解 Provider 协议 —— 给图片产出中文描述,后续走文本检索路。

为什么不直接复用 multimodal embedding(Chinese-CLIP):
- CLIP 给的是图像向量,不是自然语言描述
- 状态机里 QUERY_REWRITE 之前的 IMAGE_UNDERSTAND 需要 caption,LLM 才能消费
- CLIP 仍负责"以图搜图"的向量召回,这里负责"图 → 文",两件事

实现:
- volcengine: 走 ark.volcengineapi.com 的 doubao-1.5-vision-pro 模型
- openai: GPT-4o / GPT-4V 风格的 vision API,base_url 切换即可
- dummy: 不接 vision 时的占位,直接返回空串,让上游跳过此状态
"""

from typing import Protocol


class VisionProvider(Protocol):
    """视觉理解 Provider 接口。

    输入图片字节 + 可选 prompt,输出中文 caption / detail 描述。
    """

    name: str

    async def describe(self, image_bytes: bytes, prompt: str | None = None) -> str:
        """生成图像中文描述。

        Args:
            image_bytes: 原始图片字节(JPEG/PNG 均可,具体 provider 自己识别)
            prompt: 可选的引导提示,例如"用一句话描述商品风格+品类+颜色"

        Returns:
            纯文本描述。失败/未启用时返回空串(调用方需容错)。
        """
        ...
