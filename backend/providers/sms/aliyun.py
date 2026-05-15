"""阿里云短信 Provider —— 用官方 alibabacloud-dysmsapi20170525 SDK。

环境变量(从 .env 注入):
- SMS_ACCESS_KEY: 阿里云 AccessKey ID
- SMS_SECRET_KEY: 阿里云 AccessKey Secret
- SMS_SIGN_NAME: 签名(例如"鹿溪商城")
- SMS_TEMPLATE_CODE: 模板编码(例如 SMS_123456789)

模板示例:【鹿溪商城】您的验证码是 ${code},5 分钟内有效,请勿泄露。

SDK 是同步的(httpx 底层),用 asyncio.to_thread 适配协程。
"""

import asyncio
import json

from loguru import logger

from config import settings
from providers.sms.base import SmsProvider


class AliyunSms(SmsProvider):
    """阿里云短信服务 —— dysmsapi20170525。"""

    name = "aliyun"

    def __init__(self) -> None:
        cfg = settings.sms
        ak = cfg.access_key.get_secret_value()
        sk = cfg.secret_key.get_secret_value()
        if not (ak and sk):
            raise ValueError("阿里云 SMS 需要 SMS_ACCESS_KEY + SMS_SECRET_KEY")
        if not (cfg.sign_name and cfg.template_code):
            raise ValueError("阿里云 SMS 需要 SMS_SIGN_NAME + SMS_TEMPLATE_CODE")

        # 延迟 import:避免没装 SDK 时整个 factory 失败
        from alibabacloud_dysmsapi20170525.client import Client as DysmsClient
        from alibabacloud_tea_openapi import models as open_api_models

        config = open_api_models.Config(access_key_id=ak, access_key_secret=sk)
        # 杭州区域是默认入口,海外发送切 dysmsapi.ap-southeast-1.aliyuncs.com
        config.endpoint = "dysmsapi.aliyuncs.com"
        self._client = DysmsClient(config)
        self._sign_name = cfg.sign_name
        self._template_code = cfg.template_code

    async def send_code(self, phone: str, code: str) -> bool:
        from alibabacloud_dysmsapi20170525 import models as dysms_models

        req = dysms_models.SendSmsRequest(
            phone_numbers=phone,
            sign_name=self._sign_name,
            template_code=self._template_code,
            template_param=json.dumps({"code": code}, ensure_ascii=False),
        )

        try:
            resp = await asyncio.to_thread(self._client.send_sms, req)
        except Exception as e:  # noqa: BLE001
            logger.exception(f"aliyun_sms.network_fail phone={phone} err={e}")
            return False

        body = resp.body
        # Code == "OK" 是成功,其余都是失败(BizID 等无关字段不影响判断)
        if body and getattr(body, "code", "") == "OK":
            logger.info(f"aliyun_sms.sent phone={phone} biz_id={body.biz_id}")
            return True
        logger.warning(
            f"aliyun_sms.failed phone={phone} code={getattr(body, 'code', '?')} "
            f"msg={getattr(body, 'message', '?')}"
        )
        return False
