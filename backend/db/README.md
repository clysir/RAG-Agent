# db/ —— SQLAlchemy ORM + Alembic 迁移

> MySQL 业务库的 schema 真相源。所有表通过 ORM 定义,迁移用 Alembic autogenerate。

---

## 📂 结构

```
db/
├── __init__.py        # 暴露 Base / SessionLocal / get_session / 所有 ORM 类
├── session.py         # AsyncEngine + sessionmaker(读 settings.mysql.async_dsn)
├── models/            # 各张表的 ORM 定义
└── migrations/        # Alembic 迁移脚本(env.py 引用 db.Base.metadata)
```

---

## 📋 表清单

| 表 | 文件 | 关键字段 |
|----|------|---------|
| `users` | `models/user.py` | `id / phone (UNIQUE) / password_hash / role(user/merchant/admin) / status(active/banned) / created_at` |
| `products` | `models/product.py` | `id / merchant_id / title / category / brand / price / stock / description / attributes (JSON) / image_object_key / rating / review_count` |
| `conversations` | `models/conversation.py` | `id / user_id (nullable, 游客) / session_id / title / created_at` |
| `messages` | `models/message.py` | `id / conversation_id / role(user/assistant/system) / content / metadata (JSON) / created_at` |
| `user_memories` | `models/memory.py` | `id / user_id / fact_type / fact_text / source_msg_id / confidence / valid_from / valid_to / last_used_at / vector_id` |
| `sms_codes` | `models/sms.py`(若已加) | `id / phone / code_hash / created_at / used_at` |

---

## 🧠 重点:`user_memories` 双时态设计

灵感:Zep / mem0 / 工业事件溯源(Event Sourcing)。

```python
class UserMemory(Base):
    __tablename__ = "user_memories"

    id: Mapped[int]
    user_id: Mapped[int]                # FK
    fact_type: Mapped[FactType]         # PREFERENCE / SIZE / BRAND / BUDGET / ALLERGY / ...
    fact_text: Mapped[str]              # "用户喜欢黑色简约风"
    confidence: Mapped[float]           # LLM 抽取时给的置信度

    valid_from: Mapped[datetime]        # 何时开始生效
    valid_to: Mapped[datetime | None]   # None=当前事实;非 None=已被新版本替换
    last_used_at: Mapped[datetime]      # 最后被检索命中的时间 → 用于 decay

    source_msg_id: Mapped[int | None]   # 来自哪条对话(审计回溯)
    vector_id: Mapped[int]              # 关联 Milvus user_facts_v1 主键
```

### UPDATE 而不删
旧事实 `valid_to = now()`,新事实新行 `valid_from = now(), valid_to = None`。
查询时永远 `WHERE valid_to IS NULL`。审计回溯走 `valid_from <= t < valid_to`。

### INVALIDATE 而不删
LLM 抽到"用户不再吃辣"时,把"用户喜欢辣食"那行 `valid_to = now()`,不插新行。

### 物理删除只在 PIPL "被遗忘权" 触发时
`/memory/{fact_id}` DELETE 或 `/memory/forget-all` POST,真删 MySQL + Milvus,不留时态痕迹。

---

## 🔀 Migrations(Alembic)

`db/migrations/env.py` 关键改动:
```python
from db import Base  # 触发所有 models 导入
target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", settings.mysql.sync_dsn)  # alembic 用同步 driver
```

`db/__init__.py` 必须 import 所有 model 子模块,否则 autogenerate 找不到表:
```python
from db.session import Base, SessionLocal, get_session
from db.models import *   # noqa: F401, F403
```

`db/models/__init__.py`:
```python
from db.models.user import User
from db.models.product import Product
from db.models.conversation import Conversation
from db.models.message import Message
from db.models.memory import UserMemory, FactType
```

常用命令:
```bash
alembic revision --autogenerate -m "add user_memories"
alembic upgrade head
alembic downgrade -1
alembic history
```

---

## 🔗 Session 依赖注入

FastAPI 路由用 `Depends(get_session)`:
```python
async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as s:
        yield s
```

事务边界:
- 默认 autoflush + autocommit_block,路由结束自动 commit/rollback
- 显式跨多操作:`async with session.begin():` 手动控制

---

## 🛡️ Index 与约束

- `users.phone`:UNIQUE,登录查询走索引
- `products.category`、`products.brand`:普通索引,过滤条件常用
- `conversations.session_id`:UNIQUE,前端首次会话生成 UUID
- `messages.conversation_id + created_at`:复合索引,按会话拉历史
- `user_memories.user_id + valid_to`:复合索引,查当前事实必走

---

## 🔒 密码 hash

`users.password_hash` 存的是 bcrypt 密文,流程:
```python
# 注册
pwd_sha256 = hashlib.sha256(plain.encode()).hexdigest()  # 先 sha256 防 bcrypt 72 字节截断
hash = bcrypt.hashpw(pwd_sha256.encode(), bcrypt.gensalt(rounds=settings.auth.bcrypt_rounds))

# 登录
pwd_sha256 = hashlib.sha256(plain.encode()).hexdigest()
bcrypt.checkpw(pwd_sha256.encode(), user.password_hash)
```

不准明文存,不准换 md5/sha 替代 bcrypt。
