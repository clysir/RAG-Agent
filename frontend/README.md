# RAG-Agent · 前端

> Next.js 16 + React 19 + TypeScript + **Ant Design v6** + **Ant Design X**(AI 聊天组件)+ Zustand + TanStack Query

多模态电商导购的前端层。商品浏览 + 完整聊天页 + **悬浮聊天气泡**,与后端 FastAPI 通过 REST + **SSE 流式**对接。

---

## ✨ 关键亮点

- **AntD X 原生 AI 组件**:`Bubble` 流式气泡、`Sender` 输入框、`ThoughtChain` 状态机可视化、`Welcome` / `Prompts` 空态引导,**专为 AI 应用做的**,避免手搓
- **悬浮 + 完整双形态聊天共享 session**:浏览商品页随时唤起气泡问 AI;`/chat` 完整页消息无缝继承
- **左侧历史会话栏**(/chat 专属):登录后从 MySQL `sessions` 表拉历史,点击切换会话即时灌入消息流;**历史消息不走打字动画**(只有当前流中的占位消息 typing),刷新页面体验不再卡
- **Agent 状态机透明化**(精简版):`state_change` SSE 事件 → `ThoughtChain` 只显示"意图识别 / 多路召回 / 精排 / 生成回答"等大标题,不暴露 topK / 阈值等实现细节
- **图文输入**:拖图或点附件 → `/upload/image` 拿 `object_key` → 跟随消息发到 `/chat`
- **`assetUrl()` 自动拼接**:后端 local_fs 模式返回 `/static/...` 相对 URL,前端在 `lib/asset.ts` 统一打到 `NEXT_PUBLIC_API_BASE_URL`,UI 层不用感知
- **`<App />` 全局壳**:antd 静态 `message.xxx` / `Modal.confirm` 走动态主题 context,V6 起没这个壳会报警告
- **JWT + ApiResponse 自动解壳**:`api/client.ts` 一处搞定 Auth header / 401 清 token / 业务 code 抛错
- **dev / op 区别**:开发态直连后端 8000;生产部署可用 Next.js `rewrites()` 反代,无需改前端

---

## 🚀 快速开始

```bash
cd frontend
pnpm install
cp .env.local.example .env.local   # 默认指向 http://localhost:8000
pnpm dev                            # 起在 http://localhost:3000
```

后端先按 `backend/README.md` 把 docker-compose / 模型 / 数据 / uvicorn 准备好;前端打开就能直接交互。

生产构建:

```bash
pnpm build
pnpm start
```

---

## 📂 目录结构

```
frontend/
├── package.json            antd / @ant-design/x / zustand / @tanstack/react-query
├── next.config.ts          Next.js 配置(可加 rewrites 反代后端)
├── tsconfig.json           严格模式 + @/* 别名
├── .env.local.example      NEXT_PUBLIC_API_BASE_URL
├── public/
│   └── img-placeholder.svg 商品图占位
└── src/
    ├── app/                       Next.js App Router
    │   ├── layout.tsx             根布局:TopNav + Providers + FloatingChat
    │   ├── providers.tsx          AntdRegistry + ConfigProvider + XProvider + QueryClient
    │   ├── globals.css            少量重置 + 滚动条
    │   ├── page.tsx               首页 = Hero + 商品网格
    │   ├── chat/page.tsx          完整聊天页
    │   ├── products/[id]/page.tsx 商品详情(带"问 AI"按钮)
    │   ├── login/page.tsx         登录(账密 / 短信切 Tab)
    │   ├── register/page.tsx      普通用户注册
    │   ├── register/merchant/...  商家入驻
    │   ├── settings/memory/...    我的记忆(PIPL 合规面板,只从用户菜单进)
    │   ├── merchant/page.tsx      商家提交商品 + 我的提交列表
    │   └── admin/page.tsx         管理员审核(通过 / 驳回)
    ├── components/
    │   ├── nav/TopNav.tsx                  顶导航 + 用户菜单
    │   ├── auth/AuthHydrator.tsx           首次挂载灌 token → user
    │   ├── chat/
    │   │   ├── ChatHydrator.tsx            首次挂载 sessionId
    │   │   ├── FloatingChat.tsx            右下角气泡 → 浮窗
    │   │   ├── ChatBody.tsx                Welcome / Bubble / Sender 主体
    │   │   ├── ThoughtChainPanel.tsx       Agent 状态机可视化
    │   │   └── CitationCards.tsx           tool_output 推来的商品卡
    │   └── product/
    │       ├── ProductCard.tsx
    │       └── ProductGrid.tsx             网格 + 筛选 + 分页
    ├── lib/
    │   ├── types.ts               与 backend/schemas 一一对应的 TS 类型
    │   ├── sse.ts                 SSE 解析器(POST + FormData 走 fetch ReadableStream)
    │   ├── asset.ts               把后端相对 URL("/static/...")打到 API base
    │   ├── auth-storage.ts        localStorage 存 token + 过期判断
    │   └── api/
    │       ├── client.ts          fetch 封装(Auth header / ApiResponse 解壳 / 401 清 token)
    │       ├── auth.ts            /auth/*
    │       ├── products.ts        /products
    │       ├── upload.ts          /upload/image
    │       ├── chat.ts            POST /chat → SSE Generator + listSessions + getMessages + deleteSession
    │       ├── memory.ts          /memory/*
    │       ├── merchant.ts        /merchant/*
    │       └── admin.ts           /admin/*
    └── store/
        ├── authStore.ts           user / token / login / logout(zustand)
        └── chatStore.ts           sessionId / messages / thoughtSteps / send / abort
```

---

## 🛣️ 路由 ↔ 后端 API 映射

| 前端 | 主要后端依赖 | 备注 |
|------|------------|------|
| `/` | `GET /products` | 商品网格 + Hero |
| `/products/[id]` | `GET /products/{id}` | 详情 + "问 AI"快捷入口 |
| `/chat` | `POST /chat` (SSE) + `GET /chat/sessions` + `GET /chat/sessions/{id}/messages` + `DELETE` | 完整聊天页,左侧栏列我的会话 |
| `(浮窗)` | `POST /chat` (SSE) | 共享同一 session_id,不显示历史 |
| `/login` | `POST /auth/login` `/auth/sms/*` | 账密 + 验证码两种;管理员用 admin/admin123(`seed_admin`) |
| `/register` | `POST /auth/register` | 普通用户 |
| `/register/merchant` | `POST /auth/register/merchant` | 商家入驻 |
| `/settings/memory` | `GET / DELETE /memory/*` | **不进主导航**,从用户菜单进 |
| `/merchant` | `POST/GET /merchant/products` | 提交商品 + 我的提交(最小 UI) |
| `/admin` | `GET/POST /admin/submissions` | 通过 / 驳回(最小 UI) |
| 上传 | `POST /upload/image` | 多模态聊天 / 商品图共用 |

---

## 🔄 SSE 流式聊天的关键

后端 `POST /chat` 用 `sse-starlette` 吐 `data: {...}\n\n`,前端不能用 `EventSource`(只支持 GET),所以走 `fetch` + `ReadableStream`:

```ts
// frontend/src/lib/sse.ts
export async function* streamSSE(res: Response): AsyncGenerator<AgentEvent> {
  const reader = res.body!.getReader();
  const decoder = new TextDecoder('utf-8');
  let buf = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    // 按 "\n\n" 切块,提取 "data:" 行 JSON.parse 后 yield
  }
}
```

`chatStore.send()` 在 `for await (const ev of chatApi.stream(...))` 里分发:
- `state_change` → 推 `thoughtSteps`,驱动 `ThoughtChain`
- `tool_output` → 缓存 `pendingCitations`(retrieve / rerank 工具吐出的商品候选)
- `token` → 累加 `pendingContent`,实时滚动到当前 assistant Bubble
- `done` → 把累计的 `answer` / `citations` 落定到消息
- `error` → 写错误信息到气泡

---

## 🔌 后端契约同步

`src/lib/types.ts` 是手维护的,要和 `backend/schemas/*` 保持一致。修了后端 schema 后:

1. 改 `types.ts` 对应类型
2. 改 `src/lib/api/*.ts` 对应 endpoint(如有改名)
3. 编辑器会标红所有引用点,挨个修

后端 `ApiResponse{code,message,data}` 在 `api/client.ts` 里**自动解壳**,业务代码只拿 `data`,不需要重复处理 `code != 0`。

---

## 🎛️ 环境变量

| 变量 | 默认 | 作用 |
|------|------|------|
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | 后端基地址 |

`NEXT_PUBLIC_` 前缀是 Next.js 客户端可见环境变量的硬性要求。


---

## 📊 性能取舍

- TanStack Query `staleTime: 30s`:商品列表不频繁变,避免抖动
- `refetchOnWindowFocus: false`:聚焦不重新拉,避免覆盖正在浏览的页
- 商品图 `aspectRatio: 1/1` + `object-fit: cover`:避免 layout shift
- 思考链只在**当前正在跑或者刚跑完**这一轮显示;新一轮开始自动清空
- SSE buffer 处理:增量 decode + 按 `\n\n` 切块,大消息也不会粘包
