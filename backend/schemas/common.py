"""通用基础 schema —— 所有 API 模型继承自这里,统一时间戳、可选 id 等约定。"""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class APIModel(BaseModel):
    """所有对外 API 模型的基类 —— 启用按名/别名都能填充,序列化用别名。"""

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,  # 支持从 ORM 对象直接构造
        str_strip_whitespace=True,
    )


class Envelope(APIModel, Generic[T]):
    """统一响应外壳 —— 业务接口都返回 {code, message, data} 三段式。

    错误时 code != 0,data 为 None。前端按 code 判断成功失败。
    """

    code: int = 0
    message: str = "ok"
    data: T | None = None


class Pagination(APIModel):
    """分页元数据 —— 列表接口标配。"""

    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    total: int = 0


class PaginatedList(APIModel, Generic[T]):
    """分页列表 envelope 内的 data。"""

    items: list[T] = Field(default_factory=list)
    pagination: Pagination = Field(default_factory=Pagination)
