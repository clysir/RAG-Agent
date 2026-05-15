"""ORM 模型聚合 —— Alembic autogenerate 通过这个文件发现所有表。

import 顺序重要:被依赖的表先 import(User 是 Product / Session / Submission / Memory 的 FK 目标)。
"""

from db.models.user import User, UserRole, UserStatus
from db.models.product import Product
from db.models.conversation import Message, Session
from db.models.submission import ProductSubmission, SubmissionStatus
from db.models.memory import FactType, UserMemory

__all__ = [
    "User",
    "UserRole",
    "UserStatus",
    "Product",
    "Session",
    "Message",
    "ProductSubmission",
    "SubmissionStatus",
    "UserMemory",
    "FactType",
]
