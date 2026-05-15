"""VisionTool —— IMAGE_UNDERSTAND 状态的工具实现。

职责:
- 仅当 ctx.image_bytes 非空时调用 vision provider
- 把图像中文描述写入 ctx.image_description
- VISION_PROVIDER=disabled 时此调用为 noop,状态机直接 fallthrough 不出错

为什么状态机入口还要走这个 Tool:
- 把 vision 决策(是否启用、用哪家)统一在 provider 工厂
- 业务逻辑只关心"是否有 description",不关心提供商细节
"""

from loguru import logger

from agent.context import AgentContext
from agent.tools.base import Tool
from app.core import with_latency
from providers import get_vision


class VisionTool(Tool):
    """图像 → 中文描述。"""

    name = "vision"

    @with_latency("agent.tool.vision")
    async def execute(self, ctx: AgentContext) -> str:
        if not ctx.image_bytes:
            return ""

        try:
            vision = get_vision()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"vision.init_fail trace_id={ctx.trace_id} err={e}")
            return ""

        try:
            desc = await vision.describe(ctx.image_bytes)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"vision.describe_fail trace_id={ctx.trace_id} err={e}")
            desc = ""

        ctx.image_description = desc
        logger.info(
            f"vision.done trace_id={ctx.trace_id} "
            f"provider={vision.name} desc_len={len(desc)}"
        )
        return desc
