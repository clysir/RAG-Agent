# app/ —— FastAPI 入口层

> 网关:路由 / 中间件 / 鉴权 / 健康检查 / Celery worker

依赖方向上是**最外层**:可以 import `agent / rag / providers / db / config`,不允许反向 import。

---

## 📂 子目录

```
app/
├── __main__.py        # python -m app 入口,支持 --dev / --op CLI 覆盖
├── main.py            # FastAPI 实例化,挂中间件、异常 handler、各路由
├── api/               # 各业务路由
├── core/              # 启动、鉴权、装饰器、记忆模块
├── middleware/        # trace_id / 访问日志 / CORS
└── workers/           # Celery 应用 + 任务定义
```

---

## 🌐 API 路由(`app/api/`)

| 路由 | 文件 | 职责 |
|------|------|------|
| `POST /chat` | `chat.py` | 主接口,SSE 流式,Form data 接受 `session_id / query / image_object_key` |
| `GET /health` | `health.py` | 三依赖并行探活(MySQL / Milvus / Redis),`_PROBE_TIMEOUT=2s` |
| `POST /auth/*` | `auth.py` | 手机号+密码 / 手机号+验证码 / 注册 / refresh,JWT 签发 |
| `POST /upload/image` | `upload.py` | 用户上传图片,落对象存储,返回 `object_key` |
| `GET/POST/DELETE /memory/*` | `memory.py` | 用户长期记忆 CRUD(PIPL 合规的"被遗忘权") |
| `*/merchant/*` | `merchant.py` | 商家入驻、商品 CRUD(留接口,无审批 UI) |
| `*/admin/*` | `admin.py` | 管理员审核 + 风控(留接口) |

### `/chat` 事件流契约

```json
data: {"type": "state_change", "state": "intent", "data": null}
data: {"type": "state_change", "state": "retrieve", "data": null}
data: {"type": "state_change", "state": "rerank", "data": null}
data: {"type": "state_change", "state": "respond", "data": null}
data: {"type": "token", "state": "respond", "data": "推荐"}
data: {"type": "token", "state": "respond", "data": "如下"}
... (逐 token)
data: {"type": "done", "state": "end", "data": {"answer": "..."}}
```

- 正常路径:`state_change × N → token × N → done`
- 反问路径:`state_change × N (含 need_clarify) → token (单个反问句) → done`
- 异常路径:`state_change × N → error → done`

前端只需要监听 `token`(累加渲染)+ `state_change`(进度条)+ `done`(收尾)。

---

## 🛡️ Middleware(`app/middleware/`)

按入站顺序排列(`main.py` 注册顺序就是执行顺序):

1. **trace_id**:为每个请求生成 12 字符随机 ID,挂到 `request.state.trace_id`,贯穿所有日志
2. **access_log**:打 method/path/status/latency_ms/user_id(若已 JWT 解析)
3. **CORS**:dev 全开,op 收紧到白名单
4. **异常 handler**:`AppError` 透传 `code+message`,其它异常 op 模式脱敏成 500

---

## 🔐 鉴权(`app/core/auth.py`)

- JWT(HS256)+ bcrypt(rounds=12,先 sha256 预 hash 避免 bcrypt 72 字节截断)
- 两套依赖:
  - `get_current_user`:必需登录,401 拦截
  - `get_current_user_optional`:游客也允许(电商场景常见,匿名也能问)
- Token TTL `JWT_ACCESS_TTL_MINUTES=1440`(24h),refresh 走单独端点

---

## 🧠 记忆模块(`app/core/memory/`)

放在 app 而非 agent,因为:
- 短期(Redis 滑动窗口)是**会话级横切**,被 `/chat` 进入/退出 hook 调用,不只 agent 用
- 长期(MySQL+Milvus 双时态)由 Celery worker 异步写,被 `/memory/*` 路由 CRUD,也不只 agent 用

详细架构见 [CLAUDE.md 的"两层记忆架构"章节](../CLAUDE.md)。

文件:
- `short_term.py`:`append_turn / get_recent_turns / maybe_refresh_summary / get_slot / set_slot`
- `long_term.py`:`extract_facts / apply_facts / retrieve_facts / forget_fact / forget_all`

---

## ⚙️ Celery Worker(`app/workers/`)

```
app/workers/
├── celery_app.py      # Celery 实例 + 配置(读 settings.celery)
└── tasks.py           # 任务定义
```

任务清单:
| 任务 | 触发 | 说明 |
|------|------|------|
| `extract_user_facts` | `/chat` 收尾时 `.delay()` | LLM 抽 ADD/UPDATE/INVALIDATE 操作,写双时态 + 同步 Milvus,`max_retries=2` |
| `decay_user_memories` | beat 每天一次 | `last_used_at > LTM_DECAY_DAYS` 的事实置失效 |
| `build_index_for_product` | 商家上架商品时 `.delay()` | 单商品建索引(不阻塞 API);批量入库走 `scripts/build_index.py` |

启 worker:
```bash
celery -A app.workers.celery_app worker --loglevel=info
celery -A app.workers.celery_app beat --loglevel=info   # 衰减任务
```

---

## 🎛️ CLI 模式覆盖(`app/__main__.py`)

```bash
python -m app --dev   # 覆盖 .env 的 APP_MODE,启用 DEBUG / SQL echo / latency / 全开 CORS
python -m app --op    # 生产模式
python -m app         # 用 .env 里的 APP_MODE
```

实现:`config.settings.override_mode(...)` 在 import logging / DB engine 之前调用,避免单例缓存污染。
