"""日志配置 —— loguru 一次初始化,业务代码 from loguru import logger 直接用。

dev 模式:DEBUG 级别 + 完整 backtrace + diagnose
op 模式:INFO 级别 + 关闭 diagnose(避免变量值泄露)
"""

import sys

from loguru import logger

from config import settings


def setup_logging() -> None:
    """配置 loguru —— 模式相关参数从 settings 派生属性拿。"""
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
            "<level>{level: <7}</level> "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        ),
        backtrace=settings.is_dev,
        diagnose=settings.is_dev,  # op 关掉,避免敏感变量泄露
        enqueue=True,
    )
    logger.info(
        f"logging.init mode={settings.app_mode} level={settings.log_level} "
        f"sql_echo={settings.sql_echo} latency_log={settings.latency_log_enabled}"
    )
