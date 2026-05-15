"""短信验证码业务层 —— 把 SmsProvider + Redis + 频率限制串起来。

设计:
- 验证码生成在这里(随机数字),provider 只负责"投递"
- 三种 Redis key 形成完整防护:
  * sms:code:{phone}      验证码本体,TTL 5 分钟
  * sms:cool:{phone}      冷却期(默认 60 秒,防止刷接口)
  * sms:daily:{phone}     当日发送计数,日上限默认 10
- 校验后立即删除 code key,避免重放
"""

import secrets
from datetime import datetime, timezone

from loguru import logger

from app.core.redis_client import get_redis
from config import settings
from providers import get_sms


class SmsError(Exception):
    """业务异常 —— 路由层接住转 4xx。"""

    code: str = "sms_error"


class SmsRateLimited(SmsError):
    code = "rate_limited"


class SmsDailyExceeded(SmsError):
    code = "daily_exceeded"


class SmsCodeInvalid(SmsError):
    code = "invalid_code"


def _code_key(phone: str) -> str:
    return f"sms:code:{phone}"


def _cool_key(phone: str) -> str:
    return f"sms:cool:{phone}"


def _daily_key(phone: str) -> str:
    # 用日期前缀,过期自动清零,无需定时器
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"sms:daily:{day}:{phone}"


def _generate_code() -> str:
    """生成 N 位纯数字验证码 —— 用 secrets 保证密码学随机。"""
    n = settings.sms.code_length
    return "".join(secrets.choice("0123456789") for _ in range(n))


async def send_verification_code(phone: str) -> dict:
    """发送验证码 —— 返回 {sent: True, code?: ...}。

    mock provider 在 dev 模式下会回传 code 字段,方便前端联调;
    op 模式或真实 provider 不会回传。
    """
    cfg = settings.sms
    r = get_redis()

    # 1. 冷却期检查
    if await r.exists(_cool_key(phone)):
        ttl = await r.ttl(_cool_key(phone))
        raise SmsRateLimited(f"请 {ttl} 秒后再试")

    # 2. 当日上限检查
    daily = await r.get(_daily_key(phone))
    if daily is not None and int(daily) >= cfg.daily_limit:
        raise SmsDailyExceeded(f"今日已超过 {cfg.daily_limit} 次发送上限")

    # 3. 生成 + 写 Redis(覆盖旧 code)
    code = _generate_code()
    await r.set(_code_key(phone), code, ex=cfg.code_ttl)
    await r.set(_cool_key(phone), "1", ex=cfg.rate_limit_seconds)
    # 当日计数器,首次 set 24h 过期,后续 incr 不影响 TTL
    pipe = r.pipeline()
    pipe.incr(_daily_key(phone))
    pipe.expire(_daily_key(phone), 86400, nx=True)  # 只在不存在 TTL 时设置
    await pipe.execute()

    # 4. 投递
    provider = get_sms()
    ok = await provider.send_code(phone, code)
    if not ok:
        # 发送失败时回滚 code,避免占用配额
        await r.delete(_code_key(phone))
        raise SmsError("短信发送失败,请稍后重试")

    logger.info(f"sms.sent phone={phone} provider={provider.name}")

    # mock + dev 模式才把验证码回传方便联调,生产严禁
    result: dict = {"sent": True, "ttl": cfg.code_ttl}
    if provider.name == "mock" and settings.is_dev:
        result["code"] = code
    return result


async def verify_code(phone: str, code: str) -> bool:
    """校验验证码 —— 成功后立即删除,避免重放。"""
    r = get_redis()
    stored = await r.get(_code_key(phone))
    if stored is None:
        raise SmsCodeInvalid("验证码已过期或未发送")
    if stored != code:
        raise SmsCodeInvalid("验证码错误")
    # 校验成功立即销毁
    await r.delete(_code_key(phone))
    return True
