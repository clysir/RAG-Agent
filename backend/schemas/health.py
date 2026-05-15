"""健康检查相关 schema。"""

from schemas.common import APIModel


class DependencyStatus(APIModel):
    """单个依赖的探测结果。"""

    ok: bool = False
    latency_ms: float | None = None
    detail: str | None = None  # 失败时给原因,op 模式建议脱敏


class HealthData(APIModel):
    """健康检查的 data 部分 —— 标记服务状态、版本、关键依赖连通性。

    overall:
    - ok: 所有探针通过
    - degraded: 至少一个依赖失败(服务可启动但功能受限)
    - down: 关键依赖(mysql)失败
    """

    status: str = "ok"
    version: str = "0.1.0"
    mode: str = "dev"  # 当前运行模式 dev / op
    mysql: DependencyStatus = DependencyStatus(ok=True)
    milvus: DependencyStatus = DependencyStatus(ok=True)
    redis: DependencyStatus = DependencyStatus(ok=True)
