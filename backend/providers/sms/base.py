"""短信网关 Provider 协议 —— 业务代码只关心 send_code(phone, code)。"""

from typing import Protocol


class SmsProvider(Protocol):
    """所有短信 provider 必须实现的接口。"""

    name: str

    async def send_code(self, phone: str, code: str) -> bool:
        """发送验证码 —— 成功返回 True,失败可抛异常或返回 False。"""
        ...
