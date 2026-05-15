# schemas/ —— Pydantic Request/Response 模型

> 对外 API 的契约层。所有 `app/api/*` 的入参 / 出参都来自这里,FastAPI 自动生成 OpenAPI 文档。

---

## 📂 文件

```
schemas/
├── common.py       # 统一响应包装 ApiResponse[T] + 错误码
├── agent.py        # AgentEvent / IntentType 等(也供 agent 内部使用)
├── chat.py         # ChatRequest(form) / ChatTokenEvent / ChatStateChangeEvent
├── auth.py         # 登录 / 注册 / 验证码请求与响应
├── product.py      # 商品列表 / 详情 / 创建(merchant)
├── upload.py       # /upload/image 响应
├── health.py       # /health 响应(DependencyStatus 子模型)
└── merchant.py     # 商家相关
```

---

## 📦 统一响应壳 `ApiResponse[T]`

```python
class ApiResponse[T](BaseModel):
    code: int = 0           # 0=成功,非 0=业务错误
    message: str = "ok"
    data: T | None = None
```

所有非流式接口都返回这个壳。前端用 `code` 判断成功失败,`data` 拿业务数据。

错误码(`common.py`):
- `0` ok
- `1xxx` 校验错误(参数缺失 / 格式错)
- `2xxx` 鉴权错(401/403)
- `3xxx` 资源错(404/409)
- `5xxx` 服务端错(数据库/外部依赖)

中间件 `AppError(code, message)` → 自动包成 `ApiResponse{code, message, data: null}`。

---

## 📜 关键 schema

### `ChatRequest` (form data, 不是 JSON)

```python
session_id: str        # 前端管理的 UUID
query: str             # min_length=1, max_length=2000
image_object_key: str | None = None  # 上传图后拿到的 key
```

为什么 form 不 JSON:文件上传场景 + SSE 简单同 origin。

### `ChatEvent`(SSE 事件)

```python
class AgentEvent(BaseModel):
    type: Literal["state_change", "token", "citations", "error", "done"]
    state: AgentState | None
    data: Any | None        # token=str, state_change=null, done={answer}, citations=list
```

### `LoginRequest` 两种

```python
# 密码登录
{ phone: str, password: str }

# 验证码登录(无密码场景)
{ phone: str, code: str }
```

### `ProductOut`

```python
class ProductOut(BaseModel):
    id: int
    title: str
    description: str | None
    price: float | None
    category: str | None
    brand: str | None
    image_url: str | None      # 服务端从 image_object_key presign 出来的临时 URL
    rating: float | None
    review_count: int | None
```

**注意**:DB 里存的是 `image_object_key`,API 出参转成 `image_url`(presign 1h)。前端永远拿 URL,不知道 object key。

---

## ✅ 规范

1. **API 入参出参必须经过 schema**,不许直接返回 ORM 对象(暴露内部字段)
2. **响应字段命名 snake_case**(Python 习惯),前端约定好不要求 camelCase
3. **可选字段一律 `| None = None`**,不用 `Optional[]`
4. **List / Dict 用泛型注解**,FastAPI 自动 OpenAPI 模式
5. **不在 schema 里写业务逻辑**,只做数据 shape,业务在 service / router
