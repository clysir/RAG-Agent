"""上传相关 schema —— 文件上传后返回的引用信息。"""

from pydantic import Field

from schemas.common import APIModel


class UploadResponse(APIModel):
    """上传完成后返回 —— 前端拿 object_key 或 url 后续传给 /chat。"""

    object_key: str = Field(..., description="存储层主键,业务后续引用用这个")
    url: str = Field(..., description="可直接访问的 URL(可能是预签名)")
    size: int
    content_type: str
