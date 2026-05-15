"""空 VisionProvider —— 用于 VISION_PROVIDER=disabled 或未配 API key 时。

行为:describe() 永远返回空串。上游状态机看到空串自然跳过 IMAGE_UNDERSTAND 影响,
不让对话失败。
"""

from providers.vision.base import VisionProvider


class DisabledVision(VisionProvider):
    """禁用的 vision provider。"""

    name = "disabled"

    async def describe(self, image_bytes: bytes, prompt: str | None = None) -> str:
        return ""
