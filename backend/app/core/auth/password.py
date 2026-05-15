"""密码 hash —— 直接用 bcrypt 库,绕开 passlib 与新版 bcrypt 的兼容坑。

bcrypt 限制密码 ≤72 字节,这里在前面 UTF-8 编码后做 sha256 预 hash,
既可以接受任意长密码,又规避了 72 字节限制(常见生产实践)。
"""

import base64
import hashlib

import bcrypt

from config import settings


def _prehash(plain: str) -> bytes:
    """先 sha256 + base64,避免 bcrypt 的 72 字节限制并消除 NUL 字节问题。"""
    digest = hashlib.sha256(plain.encode("utf-8")).digest()
    return base64.b64encode(digest)  # 44 字节,远小于 72


def hash_password(plain: str) -> str:
    """加密密码 —— 返回 60 字符的 bcrypt hash 字符串。"""
    salt = bcrypt.gensalt(rounds=settings.auth.bcrypt_rounds)
    return bcrypt.hashpw(_prehash(plain), salt).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    """校验密码 —— 失败返回 False,不抛异常。"""
    try:
        return bcrypt.checkpw(_prehash(plain), hashed.encode("ascii"))
    except Exception:
        return False
