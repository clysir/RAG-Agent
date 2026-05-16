"""创建管理员账号 —— 一次性脚本,后续任何 admin 操作都用这一个账号登录。

用法:
    python -m scripts.seed_admin                       # 默认 admin / admin123
    python -m scripts.seed_admin --reset-password      # 已存在则改密码

设计:
- 管理员账号**禁止走公开注册**(/auth/register 只允许 user/merchant role)
- 这里直接绕过 API 写库,只能由部署者本机执行
- 幂等:用户名已占用时静默跳过,加 --reset-password 才覆盖
"""

import argparse
import asyncio

from loguru import logger
from sqlalchemy import select

from app.core.auth import hash_password
from db import SessionLocal, User, UserRole, UserStatus


async def main(username: str, password: str, reset_password: bool) -> None:
    async with SessionLocal() as session:
        existing = await session.scalar(select(User).where(User.username == username))
        if existing:
            if existing.role != UserRole.ADMIN:
                logger.error(
                    f"seed_admin.role_conflict username={username} current_role={existing.role.value} "
                    f"不会强改 role,请换个用户名或先手动处理"
                )
                return
            if reset_password:
                existing.password_hash = hash_password(password)
                existing.status = UserStatus.ACTIVE
                await session.commit()
                logger.warning(f"seed_admin.password_reset username={username}")
            else:
                logger.info(f"seed_admin.exists username={username} (加 --reset-password 改密码)")
            return

        admin = User(
            username=username,
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
        )
        session.add(admin)
        await session.commit()
        logger.info(
            f"seed_admin.created username={username} password={password} "
            f"role=admin status=active"
        )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="预置管理员账号 (admin / admin123)")
    p.add_argument("--username", default="admin")
    p.add_argument("--password", default="admin123")
    p.add_argument(
        "--reset-password",
        action="store_true",
        help="账号已存在时也覆盖密码(谨慎)",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(main(args.username, args.password, args.reset_password))
