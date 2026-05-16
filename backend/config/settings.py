"""配置总入口 —— 所有业务代码只能从这里读配置,禁止直接 os.getenv。

设计要点:
1. 用 pydantic-settings 自动从 .env 加载并做类型校验
2. 按子域拆 SubSettings(数据库/向量库/LLM/Embedding/Rerank/Chunking/QueryOpt/Retrieval/Celery)
3. SecretStr 保护 API Key,日志/打印不会泄露
4. APP_MODE = dev | op,横切影响日志/SQL echo/latency 上报/CORS
5. CLI --dev / --op 可在启动时通过 app/core/cli.py 覆盖,优先级高于 .env
6. 单例 settings 在进程内全局共享,直接 `from config import settings`
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

AppMode = Literal["dev", "op"]


# 所有子配置类的 env_file 配置统一 —— 不然 nested BaseSettings 不会读 .env,只会用默认值
_SUB_CONFIG = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    case_sensitive=False,
    extra="ignore",
)


class _SubSettings(BaseSettings):
    """子配置基类 —— 统一让所有 sub-settings 都从 .env 加载。"""

    model_config = _SUB_CONFIG


class MySQLSettings(_SubSettings):
    """MySQL 业务库配置 —— 商品、会话、消息等结构化数据存这里。"""

    host: str = Field("127.0.0.1", alias="MYSQL_HOST")
    port: int = Field(3306, alias="MYSQL_PORT")
    user: str = Field("rag", alias="MYSQL_USER")
    password: SecretStr = Field(SecretStr("ragpass"), alias="MYSQL_PASSWORD")
    db: str = Field("rag_agent", alias="MYSQL_DB")

    @property
    def async_dsn(self) -> str:
        pwd = self.password.get_secret_value()
        return f"mysql+aiomysql://{self.user}:{pwd}@{self.host}:{self.port}/{self.db}"

    @property
    def sync_dsn(self) -> str:
        pwd = self.password.get_secret_value()
        return f"mysql+pymysql://{self.user}:{pwd}@{self.host}:{self.port}/{self.db}"


class MilvusSettings(_SubSettings):
    """Milvus 向量库配置 —— 文本和多模态各开一个 collection。"""

    host: str = Field("127.0.0.1", alias="MILVUS_HOST")
    port: int = Field(19530, alias="MILVUS_PORT")
    text_collection: str = Field("product_text", alias="MILVUS_TEXT_COLLECTION")
    image_collection: str = Field("product_image", alias="MILVUS_IMAGE_COLLECTION")
    # 用户长期事实记忆 collection,user_id 作 partition key
    user_facts_collection: str = Field("user_facts_v1", alias="MILVUS_USER_FACTS_COLLECTION")
    text_dim: int = Field(1024, alias="MILVUS_TEXT_DIM")
    image_dim: int = Field(512, alias="MILVUS_IMAGE_DIM")


class RedisSettings(_SubSettings):
    """Redis 配置 —— 短期会话、语义缓存、Celery broker/backend 共用。"""

    host: str = Field("127.0.0.1", alias="REDIS_HOST")
    port: int = Field(6379, alias="REDIS_PORT")
    db: int = Field(0, alias="REDIS_DB")
    # Celery 用独立的 db,避免和缓存混在一起
    celery_db: int = Field(1, alias="REDIS_CELERY_DB")

    @property
    def url(self) -> str:
        return f"redis://{self.host}:{self.port}/{self.db}"

    @property
    def celery_url(self) -> str:
        return f"redis://{self.host}:{self.port}/{self.celery_db}"


class LLMSettings(_SubSettings):
    """LLM 配置 —— 业务代码用 settings.llm.model,切换 provider 改 .env。"""

    provider: Literal["deepseek", "volcengine", "openai"] = Field("deepseek", alias="LLM_PROVIDER")
    model: str = Field("deepseek-chat", alias="LLM_MODEL")
    api_key: SecretStr = Field(SecretStr(""), alias="LLM_API_KEY")
    base_url: str = Field("https://api.deepseek.com", alias="LLM_BASE_URL")
    timeout: int = Field(60, alias="LLM_TIMEOUT")


class EmbeddingSettings(_SubSettings):
    """文本 Embedding 配置 —— 默认本地 BGE-M3。"""

    provider: Literal["local_bge", "volcengine", "openai"] = Field(
        "local_bge", alias="EMBEDDING_PROVIDER"
    )
    model: str = Field("BAAI/bge-m3", alias="EMBEDDING_MODEL")
    api_key: SecretStr = Field(SecretStr(""), alias="EMBEDDING_API_KEY")
    base_url: str = Field("", alias="EMBEDDING_BASE_URL")
    # model_name 拼进 vector_id 的 hash,换模型后旧 ID 不会冲突
    version_tag: str = Field("v1", alias="EMBEDDING_VERSION_TAG")


class MMEmbeddingSettings(_SubSettings):
    """多模态 Embedding 配置 —— 用于以图搜图、图文跨模态检索。"""

    provider: Literal["local_clip", "volcengine"] = Field(
        "local_clip", alias="MM_EMBEDDING_PROVIDER"
    )
    model: str = Field("OFA-Sys/chinese-clip-vit-base-patch16", alias="MM_EMBEDDING_MODEL")
    version_tag: str = Field("v1", alias="MM_EMBEDDING_VERSION_TAG")


class RerankSettings(_SubSettings):
    """Rerank 配置 —— cross-encoder 结构精排。

    provider 选择:
    - none: 关闭精排,只用召回排序
    - local_bge: BGE 系列(FlagEmbedding),中英文强,默认 bge-reranker-v2-m3
    - cross_encoder: 通用 cross-encoder(sentence-transformers),
                     可挂任意 HF 兼容 reranker,例如 maidalun1020/bce-reranker-base_v1
    """

    provider: Literal["local_bge", "cross_encoder", "none"] = Field(
        "local_bge", alias="RERANK_PROVIDER"
    )
    model: str = Field("BAAI/bge-reranker-v2-m3", alias="RERANK_MODEL")
    # 留给最终 LLM 上下文的候选数。3-5 即可,多了会稀释 prompt 焦点。
    top_k: int = Field(5, alias="RERANK_TOP_K")


class ChunkingSettings(_SubSettings):
    """父子块切分配置 —— 离线入库专用。

    工业实践:
    - 子块小(200 字)用于精准向量召回
    - 父块大(800 字)用于命中后还原上下文,喂 LLM 时保信息完整
    - 子块通过 parent_id 指回父块,Milvus 命中后从 MySQL/缓存取父块
    """

    father_chunk_size: int = Field(800, alias="FATHER_CHUNK_SIZE")
    child_chunk_size: int = Field(200, alias="CHILD_CHUNK_SIZE")
    chunk_overlap: int = Field(50, alias="CHUNK_OVERLAP")
    # 商品类目较短时不切分,直接整段入库
    min_chunk_threshold: int = Field(100, alias="MIN_CHUNK_THRESHOLD")


class QueryOptSettings(_SubSettings):
    """Query 优化配置 —— 三种策略可独立开关。"""

    # 改写:消歧义、口语化转检索 query
    enable_rewrite: bool = Field(True, alias="QO_ENABLE_REWRITE")
    # HyDE:LLM 生成假设答案再去检索
    enable_hyde: bool = Field(False, alias="QO_ENABLE_HYDE")
    # MultiQuery:展开成多个角度的 query
    enable_multi_query: bool = Field(False, alias="QO_ENABLE_MULTI_QUERY")
    multi_query_count: int = Field(3, alias="QO_MULTI_QUERY_COUNT")


class RetrievalSettings(_SubSettings):
    """检索层配置 —— 多路召回 + 融合 + 阈值。"""

    # 各路召回 topK
    dense_top_k: int = Field(30, alias="RETRIEVAL_DENSE_TOP_K")
    sparse_top_k: int = Field(30, alias="RETRIEVAL_SPARSE_TOP_K")
    # 是否启用 BM25 稀疏召回
    enable_bm25: bool = Field(True, alias="RETRIEVAL_ENABLE_BM25")
    # RRF 融合常数,论文推荐 60
    rrf_k: int = Field(60, alias="RETRIEVAL_RRF_K")
    # 融合后送 rerank 的候选数量
    fusion_top_k: int = Field(30, alias="RETRIEVAL_FUSION_TOP_K")
    # rerank 后分数阈值,低于则丢弃(防引用噪声)
    score_threshold: float = Field(0.3, alias="RAG_SCORE_THRESHOLD")
    # 图像检索专用阈值 —— CLIP cos/IP 归一化后,陌生图(库里没有的)分数常在 0.3~0.5 之间,
    # 用文本侧的 0.3 会大量误命中。0.55 是经验值,真正"同款"通常 ≥ 0.65,"同类"在 0.55~0.65。
    image_score_threshold: float = Field(0.55, alias="RAG_IMAGE_SCORE_THRESHOLD")


class CelerySettings(_SubSettings):
    """Celery 异步任务配置 —— 独立 worker 进程。"""

    # broker 和 backend 都用 Redis,共用一个 db
    worker_concurrency: int = Field(4, alias="CELERY_CONCURRENCY")
    task_time_limit: int = Field(600, alias="CELERY_TASK_TIME_LIMIT")
    # 默认任务路由,可拓展多队列
    default_queue: str = Field("default", alias="CELERY_DEFAULT_QUEUE")


class AuthSettings(_SubSettings):
    """认证配置 —— JWT 签发、密码 hash 策略。

    生产部署务必把 JWT_SECRET 改成强随机值: openssl rand -hex 32
    """

    jwt_secret: SecretStr = Field(SecretStr("change-me-in-production"), alias="JWT_SECRET")
    jwt_algorithm: str = Field("HS256", alias="JWT_ALGORITHM")
    jwt_access_ttl_minutes: int = Field(60 * 24, alias="JWT_ACCESS_TTL_MINUTES")
    # bcrypt rounds 越高越慢但越安全,12 是常见平衡值
    bcrypt_rounds: int = Field(12, alias="BCRYPT_ROUNDS")


class StorageSettings(_SubSettings):
    """对象存储配置 —— MinIO / 本地 fs / S3 三选一。"""

    provider: Literal["minio", "local_fs", "s3"] = Field("minio", alias="STORAGE_PROVIDER")
    endpoint: str = Field("127.0.0.1:9000", alias="STORAGE_ENDPOINT")
    access_key: SecretStr = Field(SecretStr("minioadmin"), alias="STORAGE_ACCESS_KEY")
    secret_key: SecretStr = Field(SecretStr("minioadmin"), alias="STORAGE_SECRET_KEY")
    bucket: str = Field("rag-agent", alias="STORAGE_BUCKET")
    secure: bool = Field(False, alias="STORAGE_SECURE")
    region: str = Field("cn-north-1", alias="STORAGE_REGION")
    local_root: str = Field("./data/uploads", alias="STORAGE_LOCAL_ROOT")
    presign_ttl: int = Field(3600, alias="STORAGE_PRESIGN_TTL")


class SmsSettings(_SubSettings):
    """短信验证码配置 —— 抽象 provider,默认 mock 不发真短信。

    provider:
    - mock: dev 阶段用,验证码打到日志 + 通过响应回传方便联调
    - aliyun / tencent: 接真实网关(实现待补,留接口)
    """

    provider: Literal["mock", "aliyun", "tencent"] = Field("mock", alias="SMS_PROVIDER")
    access_key: SecretStr = Field(SecretStr(""), alias="SMS_ACCESS_KEY")
    secret_key: SecretStr = Field(SecretStr(""), alias="SMS_SECRET_KEY")
    sign_name: str = Field("", alias="SMS_SIGN_NAME")
    template_code: str = Field("", alias="SMS_TEMPLATE_CODE")
    code_ttl: int = Field(300, alias="SMS_CODE_TTL", description="验证码有效期(秒)")
    code_length: int = Field(6, alias="SMS_CODE_LENGTH", ge=4, le=8)
    rate_limit_seconds: int = Field(
        60, alias="SMS_RATE_LIMIT_SECONDS", description="同一手机号两次发送的最小间隔"
    )
    daily_limit: int = Field(10, alias="SMS_DAILY_LIMIT")
    # 腾讯云额外参数 —— 仅 provider=tencent 时使用
    tencent_sdk_app_id: str = Field("", alias="SMS_TENCENT_SDK_APP_ID")
    tencent_region: str = Field("ap-guangzhou", alias="SMS_TENCENT_REGION")


class MemorySettings(_SubSettings):
    """Agent 记忆配置 —— 短期 Redis / 长期 MySQL + Milvus 混合架构。

    设计依据(详见 CLAUDE.md 调研附录):
    - Mem0 论文 arXiv 2504.19413:离散事实抽取 + 异步更新
    - Letta MemGPT:OS 风格分层
    - 工业共识:短期 token 阈值 + 滚动摘要,长期条件检索
    """

    # ====== 短期记忆 ======
    # 在上下文中原文保留的最近轮数,超出走摘要
    stm_recent_turns: int = Field(8, alias="STM_RECENT_TURNS")
    # 总 token 超过这个阈值触发摘要重生成,Mem0 实验显示 27 轮以内不摘要更优
    stm_token_threshold: int = Field(1500, alias="STM_TOKEN_THRESHOLD")
    # 会话短期记忆 TTL(秒),默认 24h
    stm_ttl_seconds: int = Field(86400, alias="STM_TTL_SECONDS")

    # ====== 长期记忆 ======
    # 检索时返回的事实条数
    ltm_top_k: int = Field(5, alias="LTM_TOP_K")
    # 命中阈值,低于直接丢(防引用噪声,与 RAG_SCORE_THRESHOLD 同思路)
    ltm_score_threshold: float = Field(0.35, alias="LTM_SCORE_THRESHOLD")
    # decay 天数:无读命中超过 N 天的事实自动失效
    ltm_decay_days: int = Field(180, alias="LTM_DECAY_DAYS")
    # 是否启用长期记忆(总开关,联调/eval 时可关掉对照)
    ltm_enabled: bool = Field(True, alias="LTM_ENABLED")


class VisionSettings(_SubSettings):
    """视觉理解 (Image → Caption) Provider 配置 —— 默认 disabled,接入豆包/OpenAI 切换。

    provider:
    - disabled: 不调用任何 VLM,IMAGE_UNDERSTAND 状态直接 noop(默认,无 API key 也能跑)
    - volcengine: 火山方舟豆包视觉模型(doubao-1.5-vision-pro),OpenAI 兼容协议
    - openai: GPT-4o / GPT-4V 系列,base_url 切到 OpenAI 官方或 Azure
    """

    provider: Literal["disabled", "volcengine", "openai"] = Field(
        "disabled", alias="VISION_PROVIDER"
    )
    api_key: SecretStr = Field(SecretStr(""), alias="VISION_API_KEY")
    model: str = Field("doubao-1.5-vision-pro-32k-250115", alias="VISION_MODEL")
    base_url: str = Field("", alias="VISION_BASE_URL")
    timeout: int = Field(30, alias="VISION_TIMEOUT")
    max_tokens: int = Field(256, alias="VISION_MAX_TOKENS")


class Settings(BaseSettings):
    """全局配置聚合 —— `from config import settings` 拿实例。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ====== 模式与应用级 ======
    # APP_MODE 是横切的总开关,影响日志/SQL echo/latency/CORS
    app_mode: AppMode = Field("dev", alias="APP_MODE")
    app_host: str = Field("0.0.0.0", alias="APP_HOST")
    app_port: int = Field(8000, alias="APP_PORT")
    # log_level 留空时根据 app_mode 自动推导(dev=DEBUG, op=INFO)
    log_level_override: str = Field("", alias="LOG_LEVEL")

    # ====== 子配置 ======
    mysql: MySQLSettings = Field(default_factory=MySQLSettings)
    milvus: MilvusSettings = Field(default_factory=MilvusSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    mm_embedding: MMEmbeddingSettings = Field(default_factory=MMEmbeddingSettings)
    rerank: RerankSettings = Field(default_factory=RerankSettings)
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    query_opt: QueryOptSettings = Field(default_factory=QueryOptSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    celery: CelerySettings = Field(default_factory=CelerySettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    sms: SmsSettings = Field(default_factory=SmsSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    vision: VisionSettings = Field(default_factory=VisionSettings)

    # ====== 派生属性 —— 业务代码统一用这些 ======
    @property
    def is_dev(self) -> bool:
        return self.app_mode == "dev"

    @property
    def is_op(self) -> bool:
        return self.app_mode == "op"

    @property
    def log_level(self) -> str:
        """日志级别 —— 显式覆盖优先,否则按模式推导。"""
        if self.log_level_override:
            return self.log_level_override.upper()
        return "DEBUG" if self.is_dev else "INFO"

    @property
    def sql_echo(self) -> bool:
        """SQL 调试输出 —— 只在 dev 模式打开。"""
        return self.is_dev

    @property
    def latency_log_enabled(self) -> bool:
        """latency 装饰器是否真的打印 —— dev 全打,op 不打(交给 metrics)。"""
        return self.is_dev


@lru_cache
def get_settings() -> Settings:
    """单例工厂 —— 整个进程只加载一次 .env。"""
    s = Settings()
    _setup_hf_env()
    return s


def _setup_hf_env() -> None:
    """HuggingFace 相关环境变量 —— 必须在 import transformers/FlagEmbedding 之前生效。

    - HF_ENDPOINT: 走国内镜像加速下载
    - HF_HUB_DISABLE_XET: 关掉新版 resolve-cache 元数据接口(hf-mirror 不兼容)
    - HF_HUB_DISABLE_TELEMETRY: 关上报
    """
    import os
    from pathlib import Path

    # 默认值,可被 .env 或外部 env 覆盖
    # HF_HUB_OFFLINE=1:本项目假设模型已经通过 scripts/download_models.py 预下载,
    # 运行期不再联网。要重新拉模型时,在 .env 里设 HF_HUB_OFFLINE=0,或先跑下载脚本。
    defaults = {
        "HF_ENDPOINT": "https://hf-mirror.com",
        "HF_HUB_DISABLE_XET": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }

    # 优先读 .env,其次用 defaults
    env_path = Path(".env")
    env_file_vals: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k in defaults and v:
                env_file_vals[k] = v

    for k, default_v in defaults.items():
        # 已经在 shell 环境里设置过,尊重用户;否则用 .env,否则用 default
        if k in os.environ and os.environ[k]:
            continue
        os.environ[k] = env_file_vals.get(k, default_v)


# 业务代码统一从这里 import
settings = get_settings()


def override_mode(mode: AppMode) -> None:
    """CLI 启动时覆盖模式 —— 优先级高于 .env。

    用法见 app/core/cli.py。必须在 logging/db engine 初始化之前调用。
    """
    global settings
    # pydantic-settings 不支持运行时修改,这里直接重建一份(只重置 mode)
    new = settings.model_copy(update={"app_mode": mode})
    settings = new
    # 同步刷新 lru_cache,后续 get_settings() 也能拿到新值
    get_settings.cache_clear()
    # 重塞回缓存
    @lru_cache
    def _new_factory() -> Settings:  # noqa: D401
        return new

    globals()["get_settings"] = _new_factory
