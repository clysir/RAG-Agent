# docker/ —— 基础设施编排

> docker-compose 起 MySQL / Milvus / Redis / MinIO + etcd。

---

## 📂 文件

```
docker/
└── docker-compose.yml
```

启动:
```bash
docker compose -f docker/docker-compose.yml up -d
docker compose -f docker/docker-compose.yml ps      # 查状态
docker compose -f docker/docker-compose.yml logs -f # 看日志
docker compose -f docker/docker-compose.yml down    # 停服(保留 volume)
```

---

## 🚪 端口规划

| 服务 | 容器端口 | 主机映射 | 说明 |
|------|---------|---------|------|
| MySQL | 3306 | **3307** | 避开本机已有 MySQL,`.env` 写 `MYSQL_PORT=3307` |
| Milvus | 19530 | 19530 | gRPC |
| Milvus Web | 9091 | 9091 | metrics |
| Redis | 6379 | 6379 | |
| MinIO API | 9000 | 9000 | S3 兼容 |
| MinIO Console | 9001 | 9001 | UI(`minioadmin / minioadmin`) |
| etcd | 2379 | (内网) | Milvus 元数据 |

---

## 🛠️ 镜像 fallback 配置

国内拉 docker.io / quay.io 经常超时。配 `/etc/docker/daemon.json` 加多镜像源:

```json
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://dockerproxy.com",
    "https://docker.nju.edu.cn",
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com"
  ],
  "max-concurrent-downloads": 10,
  "max-download-attempts": 5
}
```

改完:
```bash
sudo systemctl restart docker
# 或 WSL:
sudo service docker restart
```

---

## 📦 镜像替换记录

历史踩坑:
- ❌ `milvusdb/etcd` —— 长期拉不下来,改 `quay.io/coreos/etcd:v3.5.5`
- ❌ `docker.1ms.run/...` 私镜像 —— 不稳定,移除前缀走默认 hub
- ✅ `milvusdb/milvus:v2.4.x` —— stable

如果某镜像还是拉不下来,先 `docker pull --debug` 看具体哪个 registry 失败,再单独 `docker tag` 重命名。

---

## 💾 数据持久化

compose 用命名 volume:
- `mysql_data` → MySQL `/var/lib/mysql`
- `milvus_data` → Milvus 工作目录
- `etcd_data` → etcd 数据
- `redis_data` → Redis 持久化(若开 AOF / RDB)
- `minio_data` → MinIO 对象

清理:
```bash
docker compose -f docker/docker-compose.yml down -v   # 连 volume 一起删,慎用!
```

---

## 🩺 健康检查

服务起完用 `/health` 验:
```bash
curl http://127.0.0.1:8000/health
```

返回结构(`schemas/health.py`):
```json
{
  "code": 0,
  "data": {
    "status": "ok",          // ok / degraded / down
    "mysql":  { "ok": true, "latency_ms": 14.8 },
    "milvus": { "ok": true, "latency_ms": 13.9 },
    "redis":  { "ok": true, "latency_ms": 16.0 }
  }
}
```

聚合策略:
- 三个都 ok → `status="ok"`
- mysql 挂 → `status="down"`(主库不可用)
- 仅 milvus / redis 挂 → `status="degraded"`(检索受影响但可降级)

探活并行,每个 timeout `_PROBE_TIMEOUT=2s`。

---

## ⚠️ 常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| MySQL 启动失败 / `Bind for 0.0.0.0:3306 failed` | 本机已有 MySQL | compose 改 3307 映射,`.env` 同步改 `MYSQL_PORT` |
| Milvus 起不来 | etcd 没起 / 镜像不对 | 看 `docker compose logs etcd`,可能要换 quay.io 镜像 |
| `docker-compose v1 KeyError: 'ContainerConfig'` | 旧容器引用了 retagged 镜像 | `docker rm -f <旧容器名>` 强删后重 up |
| 拉镜像超时 30 min+ | 单一 registry 故障 | 配 daemon.json 多镜像源 fallback |
| Milvus collection 找不到 / 查询返回空 | collection 未 load | `ensure_collections()` 已加 `Collection(name).load()`,新增 collection 同样要 load |
