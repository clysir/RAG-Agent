"""CLI 启动入口 —— 用 argparse 解析 --dev / --op,在 import 任何重模块前覆盖模式。

使用:
    python -m app --dev      # 开发模式
    python -m app --op       # 运行/生产模式
    python -m app            # 沿用 .env 的 APP_MODE

为什么不用 typer/click:
- 启动参数极少(就两个),用标准库 argparse 0 依赖
- 保持启动路径轻
"""

import argparse
import sys

from config import override_mode


def parse_and_apply_mode() -> None:
    """解析 CLI 参数并覆盖 settings.app_mode —— 必须在其它模块 import 之前调用。"""
    parser = argparse.ArgumentParser(add_help=False)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dev", action="store_true", help="开发模式:详尽日志、SQL echo、latency 打印")
    group.add_argument("--op", action="store_true", help="运行/生产模式:精简稳定")
    # 透传 uvicorn 的额外参数(如 --port),不在这里处理
    args, _ = parser.parse_known_args()

    if args.dev:
        override_mode("dev")
    elif args.op:
        override_mode("op")


def main() -> None:
    """python -m app 入口 —— 解析模式后启动 uvicorn。"""
    parse_and_apply_mode()

    # 故意延迟到模式覆盖之后才 import,确保 logging/db 初始化用的是正确模式
    import uvicorn

    from config import settings

    # dev 模式开 reload 方便调试,op 模式关 reload 保稳
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.is_dev,
        log_level=settings.log_level.lower(),
        # op 模式启用 access log 采样;dev 模式 access log 由我们自己的中间件接管
        access_log=settings.is_op,
    )


if __name__ == "__main__":
    main()
    sys.exit(0)
