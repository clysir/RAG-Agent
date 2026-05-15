"""火山方舟 Vision Provider —— 用 doubao-1.5-vision-pro,接 OpenAI 兼容协议。

火山方舟 API 端点:https://ark.cn-beijing.volces.com/api/v3
模型名通过控制台拿到的"接入点 ID"(endpoint),格式如 ep-2024xxxxxx-xxxxx,
不是模型本名。

参考:https://www.volcengine.com/docs/82379/1099455
"""

import base64
from typing import Any

from openai import AsyncOpenAI

from config import settings
from providers.vision.base import VisionProvider


class VolcengineVision(VisionProvider):
    """火山方舟豆包视觉模型 —— OpenAI 兼容协议。"""

    name = "volcengine_vision"

    def __init__(self) -> None:
        cfg = settings.vision
        if not cfg.api_key.get_secret_value():
            raise ValueError("VISION_API_KEY 未配置")
        self._client = AsyncOpenAI(
            api_key=cfg.api_key.get_secret_value(),
            base_url=cfg.base_url or "https://ark.cn-beijing.volces.com/api/v3",
            timeout=cfg.timeout,
        )
        self._model = cfg.model
        self._max_tokens = cfg.max_tokens

    async def describe(self, image_bytes: bytes, prompt: str | None = None) -> str:
        # 火山 vision 接口要求 base64 + data URL 格式
        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:image/jpeg;base64,{b64}"

        user_prompt = prompt or (
            "请用一句话描述这张商品图片,包含品类、颜色、风格、关键材质。"
            "只输出描述本身,不要解释。"
        )
        # 用 OpenAI 多模态消息格式:content 是 list[dict],含 text + image
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
