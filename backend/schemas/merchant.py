"""商家/审核相关 schema。"""

from pydantic import Field

from schemas.common import APIModel


class SubmitProductRequest(APIModel):
    """商家提交商品入参 —— 图片单独走 multipart 上传,这里只带 object_key。"""

    title: str = Field(..., min_length=1, max_length=512)
    category: str = Field(..., min_length=1, max_length=128)
    price: float = Field(..., ge=0)
    brand: str | None = None
    description: str | None = None
    stock: int = 0
    image_object_key: str | None = Field(None, description="先调 /upload 拿 object_key 再传")
    attributes: dict | None = None


class SubmissionBrief(APIModel):
    """提交记录简要 —— 列表用。"""

    id: int
    merchant_id: int
    title: str
    category: str
    price: float
    status: str
    image_url: str | None = None  # 服务端 presign 后返回
    created_at: str  # ISO 时间字符串


class RejectSubmissionRequest(APIModel):
    """驳回入参 —— 必须填理由,商家可见。"""

    reason: str = Field(..., min_length=1, max_length=512)


class BanUserRequest(APIModel):
    """封禁用户入参 —— 可选写理由。"""

    reason: str | None = Field(None, max_length=256)
