"""短信 provider 工厂 —— 按 settings.sms.provider 选实现。"""

from functools import lru_cache

from config import settings
from providers.sms.base import SmsProvider


@lru_cache
def get_sms() -> SmsProvider:
    """短信 provider 单例。"""
    provider = settings.sms.provider
    if provider == "mock":
        from providers.sms.mock import MockSms

        return MockSms()
    if provider == "aliyun":
        from providers.sms.aliyun import AliyunSms

        return AliyunSms()
    if provider == "tencent":
        from providers.sms.tencent import TencentSms

        return TencentSms()
    raise ValueError(f"未知 SMS provider: {provider}")
