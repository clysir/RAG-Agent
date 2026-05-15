"""腾讯云短信 Provider —— 用官方 tencentcloud-sdk-python。

环境变量:
- SMS_ACCESS_KEY: 腾讯云 SecretId
- SMS_SECRET_KEY: 腾讯云 SecretKey
- SMS_SIGN_NAME: 签名(腾讯云控制台审核通过的签名内容)
- SMS_TEMPLATE_CODE: 模板 ID(数字)
- SMS_TENCENT_SDK_APP_ID: 短信 SdkAppId(数字,自配)
- SMS_TENCENT_REGION: 区域,默认 ap-guangzhou

腾讯云模板示例:您的验证码为 {1},5 分钟内有效。如非本人操作请忽略。
"""

import asyncio

from loguru import logger

from config import settings
from providers.sms.base import SmsProvider


class TencentSms(SmsProvider):
    """腾讯云短信 —— SmsClient。"""

    name = "tencent"

    def __init__(self) -> None:
        cfg = settings.sms
        ak = cfg.access_key.get_secret_value()
        sk = cfg.secret_key.get_secret_value()
        if not (ak and sk):
            raise ValueError("腾讯云 SMS 需要 SMS_ACCESS_KEY + SMS_SECRET_KEY")
        if not (cfg.sign_name and cfg.template_code):
            raise ValueError("腾讯云 SMS 需要 SMS_SIGN_NAME + SMS_TEMPLATE_CODE")
        if not cfg.tencent_sdk_app_id:
            raise ValueError("腾讯云 SMS 需要 SMS_TENCENT_SDK_APP_ID")

        from tencentcloud.common import credential
        from tencentcloud.common.profile.client_profile import ClientProfile
        from tencentcloud.common.profile.http_profile import HttpProfile
        from tencentcloud.sms.v20210111 import sms_client

        cred = credential.Credential(ak, sk)
        http_profile = HttpProfile()
        http_profile.endpoint = "sms.tencentcloudapi.com"
        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile

        self._client = sms_client.SmsClient(cred, cfg.tencent_region, client_profile)
        self._sdk_app_id = cfg.tencent_sdk_app_id
        self._sign_name = cfg.sign_name
        self._template_id = cfg.template_code

    async def send_code(self, phone: str, code: str) -> bool:
        from tencentcloud.sms.v20210111 import models

        # 腾讯云手机号要求 +86 前缀
        phone_norm = phone if phone.startswith("+") else f"+86{phone}"

        req = models.SendSmsRequest()
        req.SmsSdkAppId = self._sdk_app_id
        req.SignName = self._sign_name
        req.TemplateId = self._template_id
        req.TemplateParamSet = [code]
        req.PhoneNumberSet = [phone_norm]

        try:
            resp = await asyncio.to_thread(self._client.SendSms, req)
        except Exception as e:  # noqa: BLE001
            logger.exception(f"tencent_sms.network_fail phone={phone} err={e}")
            return False

        # SendStatusSet 每条消息一个结果,Code == "Ok" 才算成功
        for st in resp.SendStatusSet or []:
            if st.Code != "Ok":
                logger.warning(
                    f"tencent_sms.failed phone={phone} code={st.Code} msg={st.Message}"
                )
                return False
        logger.info(f"tencent_sms.sent phone={phone}")
        return True
