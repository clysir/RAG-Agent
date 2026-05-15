# config/ —— 单一配置入口

> 项目所有配置只能从 `config/settings.py` 读。**禁止业务代码 `os.getenv`、硬编码 URL / 模型名 / chunk 大小**。

---

## 📂 文件

```
config/
├── __init__.py     # from . import settings 暴露单例
└── settings.py     # 所有 sub-settings + Settings 聚合 + override_mode
```

---

## 🧱 设计:分层 sub-settings + `_SubSettings` 基类

```python
_SUB_CONFIG = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8",
                                  case_sensitive=False, extra="ignore")

class _SubSettings(BaseSettings):
    """子配置基类 —— 不可省,见下面陷阱说明"""
    model_config = _SUB_CONFIG

class MySQLSettings(_SubSettings):
    host: str = Field("127.0.0.1", alias="MYSQL_HOST")
    port: int = Field(3306, alias="MYSQL_PORT")
    ...

class Settings(BaseSettings):
    mysql: MySQLSettings = Field(default_factory=MySQLSettings)
    milvus: MilvusSettings = Field(default_factory=MilvusSettings)
    ...
```

### ⚠️ 陷阱:不继承 `_SubSettings` 会静默忽略 .env

直接 `class MySQLSettings(BaseSettings)` 会**不读** `.env`,所有 `Field(...)` 默认值生效。
现象:`.env` 里 `MYSQL_PORT=3307` 写了,运行起来还是 3306,连不上 Docker。

**唯一可靠做法是声明 `_SubSettings` 基类共享 `model_config`,所有子配置继承它。**
新增 sub-settings 务必 `class NewSettings(_SubSettings)`,不要直接继承 `BaseSettings`。

---

## 📦 现有 sub-settings

| 类 | 前缀 | 主要字段 |
|----|-----|---------|
| `MySQLSettings` | `MYSQL_*` | host / port / user / password / db,`async_dsn` / `sync_dsn` 派生属性 |
| `MilvusSettings` | `MILVUS_*` | host / port / text_collection / image_collection / user_facts_collection / dims |
| `RedisSettings` | `REDIS_*` | host / port / db / celery_db,`url` / `celery_url` 派生 |
| `LLMSettings` | `LLM_*` | provider / model / api_key (SecretStr) / base_url / timeout |
| `EmbeddingSettings` | `EMBEDDING_*` | provider / model / version_tag |
| `MMEmbeddingSettings` | `MM_EMBEDDING_*` | provider / model / version_tag |
| `RerankSettings` | `RERANK_*` | provider / model / top_k |
| `ChunkingSettings` | `*_CHUNK_*` | father_chunk_size / child_chunk_size / overlap / min_threshold |
| `QueryOptSettings` | `QO_*` | enable_rewrite / enable_hyde / enable_multi_query / multi_query_count |
| `RetrievalSettings` | `RETRIEVAL_*` / `RAG_SCORE_THRESHOLD` | dense_top_k / sparse_top_k / rrf_k / fusion_top_k / score_threshold |
| `CelerySettings` | `CELERY_*` | concurrency / time_limit / default_queue |
| `AuthSettings` | `JWT_*` / `BCRYPT_*` | jwt_secret / algorithm / ttl / bcrypt_rounds |
| `StorageSettings` | `STORAGE_*` | provider / endpoint / access_key / secret_key / bucket / region / presign_ttl |
| `SmsSettings` | `SMS_*` | provider / access_key / secret_key / sign_name / template_code / TTL / rate_limit |
| `MemorySettings` | `STM_*` / `LTM_*` | stm_recent_turns / stm_token_threshold / ltm_top_k / ltm_score_threshold / ltm_decay_days / ltm_enabled |
| `VisionSettings` | `VISION_*` | provider / api_key / model / base_url / timeout / max_tokens |

---

## 🎛️ dev / op 双模式

```python
settings.app_mode  # Literal["dev", "op"]
settings.is_dev    # bool
settings.is_op     # bool
settings.log_level # "DEBUG" if dev else "INFO"(可被 LOG_LEVEL env 覆盖)
settings.sql_echo  # 只在 dev 打 SQL
settings.latency_log_enabled  # 只在 dev 打 latency,op 走采样上报
```

CLI 覆盖:
```bash
python -m app --dev   # → override_mode("dev")
python -m app --op    # → override_mode("op")
```

`override_mode` 必须在 logging / DB engine 初始化前调用,内部清掉 `lru_cache` 并重建单例。

---

## 🔐 SecretStr 防泄

所有密钥字段用 `pydantic.SecretStr`:
- `LLM_API_KEY`, `JWT_SECRET`, `MYSQL_PASSWORD`, `STORAGE_SECRET_KEY`, `SMS_SECRET_KEY`, `VISION_API_KEY`
- `print(settings)` / 日志输出会显示 `SecretStr('**********')`,不会泄露明文
- 业务代码取明文用 `.get_secret_value()`(只在拼 DSN / 请求 header 时)

---

## 🌐 HuggingFace 环境(`_setup_hf_env`)

在 `get_settings()` 首次调用时执行,**必须在 import transformers / FlagEmbedding 之前**:

| 变量 | 默认 | 作用 |
|-----|------|-----|
| `HF_ENDPOINT` | `https://hf-mirror.com` | 走国内镜像加速下载 |
| `HF_HUB_DISABLE_XET` | `1` | 关掉新版 resolve-cache 接口(hf-mirror 不兼容) |
| `HF_HUB_DISABLE_TELEMETRY` | `1` | 关上报 |
| `HF_HUB_OFFLINE` | `1` | 运行期不联网(模型应通过 `scripts/download_models.py` 预下载) |
| `TRANSFORMERS_OFFLINE` | `1` | 同上 |

优先级:`os.environ` 已有 > `.env` 文件 > 默认值。

要重新拉模型时改 `HF_HUB_OFFLINE=0`,或先跑下载脚本。

---

## ✅ 使用规范

```python
# ✓ 正确
from config import settings
dsn = settings.mysql.async_dsn
threshold = settings.retrieval.score_threshold

# ✗ 错误
import os
dsn = f"mysql://{os.getenv('MYSQL_HOST')}..."  # 绕过类型校验和 SecretStr

# ✗ 错误
from config.settings import Settings
s = Settings()  # 绕过 lru_cache 和 _setup_hf_env,会重复加载
```
