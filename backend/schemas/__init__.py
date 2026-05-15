"""API schemas 包入口 —— 按域分文件,对外只暴露具体类型。"""

from schemas.agent import AgentStateName, AgentStreamEvent, EventType, ProductCard
from schemas.auth import (
    CurrentUser,
    LoginRequest,
    RegisterMerchantRequest,
    RegisterRequest,
    SmsLoginRequest,
    SmsSendRequest,
    SmsSendResponse,
    TokenResponse,
)
from schemas.chat import (
    ChatRequest,
    CreateSessionRequest,
    MessageRecord,
    SessionInfo,
)
from schemas.common import APIModel, Envelope, PaginatedList, Pagination
from schemas.health import DependencyStatus, HealthData
from schemas.merchant import (
    BanUserRequest,
    RejectSubmissionRequest,
    SubmissionBrief,
    SubmitProductRequest,
)
from schemas.product import (
    IngestProductRequest,
    ProductBrief,
    ProductDetail,
    ProductSearchRequest,
)
from schemas.upload import UploadResponse

__all__ = [
    "APIModel",
    "Envelope",
    "Pagination",
    "PaginatedList",
    "AgentStateName",
    "AgentStreamEvent",
    "EventType",
    "ProductCard",
    "RegisterRequest",
    "RegisterMerchantRequest",
    "LoginRequest",
    "SmsSendRequest",
    "SmsSendResponse",
    "SmsLoginRequest",
    "TokenResponse",
    "CurrentUser",
    "ChatRequest",
    "CreateSessionRequest",
    "SessionInfo",
    "MessageRecord",
    "ProductBrief",
    "ProductDetail",
    "ProductSearchRequest",
    "IngestProductRequest",
    "HealthData",
    "DependencyStatus",
    "UploadResponse",
    "SubmitProductRequest",
    "SubmissionBrief",
    "RejectSubmissionRequest",
    "BanUserRequest",
]
