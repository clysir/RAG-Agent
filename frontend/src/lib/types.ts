/**
 * 前端 TypeScript 类型 —— 与 backend/schemas/* Pydantic 模型一一对应。
 * 后端契约变了,这里也要跟着改。
 */

// ============= 统一响应壳 =============
export type ApiResponse<T> = {
  code: number; // 0=成功,非 0=业务错误
  message: string;
  data: T | null;
};

// ============= 认证 =============
export type UserRole = 'user' | 'merchant' | 'admin';
export type UserStatus = 'active' | 'banned';

export interface CurrentUser {
  id: number;
  username?: string | null;
  email?: string | null;
  phone?: string | null;
  role: UserRole;
  status: UserStatus;
  shop_name?: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: 'bearer';
  expires_in: number; // 秒
}

export interface RegisterRequest {
  username: string;
  email?: string;
  password: string;
}

export interface MerchantRegisterRequest extends RegisterRequest {
  shop_name: string;
  business_license: string;
}

export interface SmsLoginRequest {
  phone: string;
  code: string;
}

// ============= 商品 =============
export interface ProductOut {
  id: number;
  title: string;
  description?: string | null;
  price?: number | null;
  category?: string | null;
  brand?: string | null;
  image_url?: string | null;
  rating?: number | null;
  review_count?: number | null;
}

export interface ProductListParams {
  page?: number;
  page_size?: number;
  category?: string;
  brand?: string;
  min_price?: number;
  max_price?: number;
  q?: string; // 简单关键词搜索(可选)
}

export interface ProductListResponse {
  items: ProductOut[];
  total: number;
  page: number;
  page_size: number;
}

// ============= 上传 =============
export interface UploadResponse {
  object_key: string;
  url: string; // 上传后的可访问 URL(presign)
  size: number;
  content_type: string;
}

// ============= Agent 状态机 + SSE 事件 =============
export type AgentState =
  | 'intent'
  | 'load_memory'
  | 'image_understand'
  | 'query_rewrite'
  | 'retrieve'
  | 'rerank'
  | 'web_fallback'
  | 'need_clarify'
  | 'respond'
  | 'end';

// 召回 / rerank 工具吐出的商品候选
export interface ProductCard {
  product_id: number;
  title: string;
  score: number;
  price?: number | null;
  image_url?: string | null;
  snippet?: string | null;
  extra?: Record<string, unknown> | null;
}

// 联网搜索结果(WEB_FALLBACK 状态产出)
export interface WebSource {
  title: string;
  url: string;
  snippet?: string;
  source?: string;          // 域名,如 nike.com.cn
  publish_date?: string | null;
}

// SSE 事件类型联合体 —— 后端 schemas/agent.py 的 AgentEvent 翻译
export type AgentEvent =
  | { type: 'state_change'; state: AgentState; data?: null }
  | { type: 'tool_output'; state: AgentState; data: { count: number; products: ProductCard[] } }
  | { type: 'token'; state?: AgentState; data: string }
  | { type: 'citations'; data: ProductCard[] }
  | { type: 'error'; data: { msg: string } }
  | { type: 'done'; data: { answer: string; citations?: ProductCard[]; web_sources?: WebSource[] } };

// 前端聊天消息(本地维护,不在后端 schema 里)
export interface ChatMessage {
  id: string; // 前端生成 uuid
  role: 'user' | 'assistant';
  content: string;
  image_url?: string | null; // user 消息附带的图(展示用)
  citations?: ProductCard[]; // assistant 消息引用的商品卡
  web_sources?: WebSource[]; // 联网兜底时的网搜来源
  created_at: number; // unix ms
  /** 当前轮正在 SSE 中的 assistant 占位消息为 true;历史 / 收尾后为 false。
   *  用来控制 Bubble 的 typing 动画 —— 历史消息不该再有打字过场。 */
  streaming?: boolean;
}

// 历史会话(后端 GET /chat/sessions)
export interface SessionBrief {
  id: string;
  title?: string | null;
  message_count: number;
  updated_at: string;
  created_at: string;
}

// 历史消息(后端 GET /chat/sessions/{id}/messages)
export interface MessageOut {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  image_url?: string | null;
  created_at: string;
}

// ============= 记忆 =============
export type FactType =
  | 'PREFERENCE'
  | 'SIZE'
  | 'BRAND'
  | 'BUDGET'
  | 'ALLERGY'
  | 'OCCUPATION'
  | 'OTHER';

export interface MemoryItem {
  id: number;
  fact_type: FactType;
  fact_text: string;
  confidence: number;
  valid_from: string; // ISO datetime
  valid_to?: string | null;
  source_msg_id?: number | null;
}

export interface MemoryList {
  items: MemoryItem[];
  total: number;
}

// ============= 商家 =============
export type SubmissionStatus = 'pending' | 'approved' | 'rejected';

export interface SubmissionBrief {
  id: number;
  merchant_id: number;
  title: string;
  category: string;
  price: number;
  status: SubmissionStatus;
  image_url?: string | null;
  created_at: string;
}

export interface MerchantSubmitRequest {
  title: string;
  category: string;
  price: number;
  brand?: string;
  description?: string;
  stock: number;
  image_object_key?: string;
}

// ============= 健康 =============
export interface DependencyStatus {
  ok: boolean;
  latency_ms: number;
}

export interface HealthData {
  status: 'ok' | 'degraded' | 'down';
  mode: 'dev' | 'op';
  mysql: DependencyStatus;
  milvus: DependencyStatus;
  redis: DependencyStatus;
}
