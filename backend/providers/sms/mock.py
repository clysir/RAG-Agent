"""Mock 短信 provider —— dev 阶段用,不真发,把验证码打到日志方便联调。

设计细节:
- send_code 直接返回 True
- 验证码并不在这里存,而是在 Redis 里(由 auth 路由统一管理),
  这里只负责"发送"动作的抽象
- 日志显式打印验证码,在 dev 模式 latency_log_enabled=True 时还会带 latency
"""

from loguru import logger

from providers.sms.base import SmsProvider


class MockSms(SmsProvider):
    name = "mock"

    async def send_code(self, phone: str, code: str) -> bool:
        # 故意把 code 打在 WARNING 级别,即便 op 模式也能看到(避免 dev 误切 op 后调试卡住)
        logger.warning(f"[MOCK-SMS] phone={phone} code={code} (验证码已模拟发送,实际未发)")
        return True
