"""OpenAI Vision Provider —— GPT-4o / GPT-4V 多模态。

与 Volcengine 结构一致,只是 base_url 默认走 OpenAI 官方。
任何 OpenAI 兼容的 vision 端点(Together / Anyscale / Azure)都可通过改 base_url 走此实现。
"""

import base64
from typing import Any

from openai import AsyncOpenAI

from config import settings
from providers.vision.base import VisionProvider


class OpenAIVision(VisionProvider):
    """OpenAI 视觉模型 —— GPT-4o / GPT-4 Turbo Vision。"""

    name = "openai_vision"

    def __init__(self) -> None:
        cfg = settings.vision
        if not cfg.api_key.get_secret_value():
            raise ValueError("VISION_API_KEY 未配置")
        self._client = AsyncOpenAI(
            api_key=cfg.api_key.get_secret_value(),
            base_url=cfg.base_url or "https://api.openai.com/v1",
            timeout=cfg.timeout,
        )
        self._model = cfg.model
        self._max_tokens = cfg.max_tokens

    async def describe(self, image_bytes: bytes, prompt: str | None = None) -> str:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:image/jpeg;base64,{b64}"
        user_prompt = prompt or (
            "请用一句话中文描述这张商品图片,包含品类、颜色、风格、关键材质。只输出描述本身。"
        )
        content: list[dict[str, Any]] = [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": content}],
            temperature=0.2,
            max_tokens=self._max_tokens,
            stream=False,
        )
        return (resp.choices[0].message.content or "").strip()
