"""商品相关 schema —— 列表查询、详情、入库等接口用。"""

from pydantic import Field

from schemas.common import APIModel


class ProductBrief(APIModel):
    """商品简略信息 —— 列表/卡片场景用。"""

    id: int
    title: str
    category: str
    price: float
    image_url: str | None = None
    rating: float | None = None


class ProductDetail(ProductBrief):
    """商品详情 —— 详情页用。"""

    brand: str | None = None
    description: str | None = None
    stock: int = 0
    review_count: int = 0
    attributes: dict | None = None


class ProductSearchRequest(APIModel):
    """商品过滤检索入参 —— 非语义,纯结构化,后台管理或前端筛选用。"""

    keyword: str | None = None
    category: str | None = None
    brand: str | None = None
    min_price: float | None = Field(None, ge=0)
    max_price: float | None = Field(None, ge=0)
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class IngestProductRequest(APIModel):
    """商品入库入参 —— POST /admin/products,后台/批量任务用。"""

    title: str = Field(..., min_length=1, max_length=512)
    category: str = Field(..., min_length=1, max_length=128)
    price: float = Field(..., ge=0)
    brand: str | None = None
    description: str | None = None
    stock: int = 0
    image_url: str | None = None
    attributes: dict | None = None
