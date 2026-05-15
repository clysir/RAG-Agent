# providers/ —— 外部依赖抽象层

> 所有外部服务(LLM / Embedding / Rerank / Vision / Storage / SMS)都走协议 + 工厂模式。
> **业务代码只依赖协议,不直接 import 具体 SDK。** 切 provider 只改 `.env`。

---

## 📂 子目录(每个都是一组协议 + 多个实现 + 工厂)

```
providers/
├── llm/         deepseek.py / volcengine.py / openai.py
├── embedding/   local_bge.py / local_clip.py / volcengine.py
├── rerank/      local_bge.py / cross_encoder.py / none.py
├── vision/      disabled.py / volcengine.py / openai.py
├── storage/     minio.py / s3.py / local_fs.py
└── sms/         mock.py / aliyun.py / tencent.py
```

---

## 🧬 协议(每个子目录都有 `base.py`)

```python
# llm/base.py
class LLMProvider(Protocol):
    async def chat(self, messages, stream=False, **kw) -> AsyncIterator[str] | LLMResponse: ...

# embedding/base.py
class EmbeddingProvider(Protocol):
    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

class MultiModalEmbeddingProvider(EmbeddingProvider):
    async def embed_images(self, images: list[bytes]) -> list[list[float]]: ...

# rerank/base.py
class RerankProvider(Protocol):
    async def rerank(self, query: str, docs: list[str]) -> list[float]: ...

# vision/base.py
class VisionProvider(Protocol):
    async def describe(self, image: bytes, prompt: str | None = None) -> str: ...

# storage/base.py
class StorageProvider(Protocol):
    async def put(self, key: str, data: bytes, content_type: str = ...) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def presign_url(self, key: str, ttl_seconds: int = ...) -> str: ...
    async def delete(self, key: str) -> None: ...

# sms/base.py
class SmsProvider(Protocol):
    async def send_code(self, phone: str, code: str) -> None: ...
```

---

## 🏭 工厂(`providers/__init__.py`)

```python
from providers import (
    get_llm,                # → LLMProvider 单例
    get_text_embedder,      # → EmbeddingProvider 单例
    get_image_embedder,     # → MultiModalEmbeddingProvider 单例
    get_reranker,           # → RerankProvider 单例
    get_vision,             # → VisionProvider 单例
    get_storage,            # → StorageProvider 单例
    get_sms,                # → SmsProvider 单例
)
```

工厂内部:`@lru_cache` 单例 + 按 `settings.<sub>.provider` 选实现。

---

## 🎯 各 provider 默认值与可选

| Provider | 默认 | 可选 | 切换 |
|---------|------|-----|------|
| LLM | `deepseek` (`deepseek-v4-flash`) | `volcengine` / `openai` | 改 `LLM_PROVIDER` |
| Text Embedding | `local_bge` (`BAAI/bge-m3`, 1024D) | `volcengine` / `openai` | `EMBEDDING_PROVIDER` |
| MM Embedding | `local_clip` (`OFA-Sys/chinese-clip-vit-base-patch16`, 512D) | `volcengine` | `MM_EMBEDDING_PROVIDER` |
| Rerank | `local_bge` (`BAAI/bge-reranker-v2-m3`) | `cross_encoder` / `none` | `RERANK_PROVIDER` |
| Vision | `disabled` | `volcengine` (豆包) / `openai` (GPT-4o) | `VISION_PROVIDER` |
| Storage | `local_fs` | `minio` / `s3` (兼容 Aliyun OSS / 腾讯 COS / R2) | `STORAGE_PROVIDER` |
| SMS | `mock` | `aliyun` / `tencent` | `SMS_PROVIDER` |

---

## ⚠️ 实现注意事项

### LLM
- `LLMResponse` 含 `content / usage`(prompt_tokens / completion_tokens),用于打日志
- 流式返回 `AsyncIterator[str]`,每个 yield 一个 token delta
- 火山方舟、OpenAI 复用 `AsyncOpenAI` SDK(OpenAI 兼容协议)

### Embedding(local)
- 惰性加载:第一次调用才 `from_pretrained`,避免启动延迟
- `_lazy_load()` 设 fp16 (GPU) / fp32 (CPU)
- 推理走 `asyncio.to_thread`,不阻塞 event loop
- BGE-M3 内部 batch_size 自适应,我们外面一次喂多条即可

### Rerank
- 老 `BGE-Reranker` 在某些版本下 `pooler_output=None`,fallback 用 `[CLS]` hidden state
- `none` 实现直接返回原顺序的分数(用于关掉精排做 A/B)

### Vision
- `disabled`:返回空字符串,`IMAGE_UNDERSTAND` 状态直接 noop(默认行为,无 API key 也能跑)
- `volcengine` / `openai`:base64 转 data URL 喂 multimodal chat completion

### Storage
- `local_fs`:简单文件系统,**只用于 dev**;`object_key` 按 `/` 分层映射目录
- `minio`:aiobotocore 兼容
- `s3`:aioboto3 + SigV4 + IAM Role,兼容 Aliyun OSS / 腾讯 COS / Cloudflare R2(改 `STORAGE_ENDPOINT`)
- presign URL TTL 默认 1h(`STORAGE_PRESIGN_TTL`)

### SMS
- `mock`:**dev 默认**。验证码打到日志 + 通过响应体回传方便联调
- `aliyun`:`alibabacloud_dysmsapi20170525` SDK,要 `sign_name + template_code`
- `tencent`:`tencentcloud-sdk-python` SDK,要 `sdk_app_id + region`

---

## 🧪 如何新增 Provider

例:接入 Claude API。

1. 写 `providers/llm/claude.py`,实现 `LLMProvider.chat`
2. 在 `providers/llm/factory.py`(或 `__init__.py`)的工厂里加分支:
   ```python
   if provider == "claude":
       from providers.llm.claude import ClaudeLLM
       return ClaudeLLM()
   ```
3. `config/settings.py` 的 `LLMSettings.provider` Literal 加 `"claude"`
4. `.env.example` 加一行注释说明
5. 跑 `python -m scripts.test_models` 验证

**不要**在业务代码里写 `if provider == "claude": ...`,只在工厂分流。
