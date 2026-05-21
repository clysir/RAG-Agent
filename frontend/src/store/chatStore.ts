/**
 * 聊天全局状态:悬浮气泡 + 完整聊天页共享同一份 store(同一 session_id)。
 *
 *   - sessionId: 启动时 localStorage 取,没有就生成 UUID 并写回
 *   - messages: 历史对话(user + assistant 交替)
 *   - thoughtSteps: 当前正在进行的一轮的状态机轨迹,用于 AntD X ThoughtChain
 *   - pendingAssistantContent: token 事件累积成的"打字中"内容
 *   - pendingCitations: tool_output 事件吐出的商品卡,done 时 attach 到消息
 */

'use client';

import { create } from 'zustand';
import { chatApi } from '../lib/api/chat';
import { assetUrl } from '../lib/asset';
import type { AgentEvent, AgentState, ChatMessage, ProductCard } from '../lib/types';

const SESSION_KEY = 'rag_chat_session';

function getOrCreateSession(): string {
  if (typeof window === 'undefined') return 'ssr-placeholder';
  const existing = localStorage.getItem(SESSION_KEY);
  if (existing) return existing;
  const sid = crypto.randomUUID();
  localStorage.setItem(SESSION_KEY, sid);
  return sid;
}

export type StepStatus = 'pending' | 'running' | 'done';

export interface ThoughtStep {
  state: AgentState;
  status: StepStatus;
  /** 进入 / 离开的时间戳,用于显示耗时 */
  startedAt?: number;
  endedAt?: number;
}

interface ChatState {
  sessionId: string;
  hydrated: boolean;

  messages: ChatMessage[];

  isStreaming: boolean;
  /** 当前正在跑的一轮的思考链(只一轮的,新一轮会重置) */
  thoughtSteps: ThoughtStep[];
  /** 正在累积的 assistant 文本 */
  pendingContent: string;
  /** 正在累积的引用商品 */
  pendingCitations: ProductCard[];

  /** 悬浮气泡是否展开 */
  floatingOpen: boolean;
}

interface ChatActions {
  hydrate: () => void;
  send: (query: string, imageObjectKey?: string, userImageUrl?: string | null) => Promise<void>;
  abort: () => void;
  resetSession: () => void;
  /** 切到一个已有会话:写 sessionId + 从后端拉历史消息灌进 messages。 */
  switchSession: (sessionId: string) => Promise<void>;
  /** 仅拉当前 sessionId 的历史(/chat 页面挂载时刷新一下),静默失败。 */
  loadHistoryForCurrent: () => Promise<void>;
  toggleFloating: (open?: boolean) => void;
}

// 单例 AbortController,新对话开始时如果上一轮还没完就 abort
let activeController: AbortController | null = null;

function makeMsg(role: 'user' | 'assistant', content: string, extra: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role,
    content,
    created_at: Date.now(),
    ...extra,
  };
}

export const useChatStore = create<ChatState & ChatActions>((set, get) => ({
  sessionId: '',
  hydrated: false,

  messages: [],

  isStreaming: false,
  thoughtSteps: [],
  pendingContent: '',
  pendingCitations: [],

  floatingOpen: false,

  hydrate() {
    if (get().hydrated) return;
    set({ sessionId: getOrCreateSession(), hydrated: true });
  },

  async send(query, imageObjectKey, userImageUrl) {
    const { sessionId, isStreaming } = get();
    if (!sessionId) {
      console.warn('[chat] sessionId 未就绪');
      return;
    }
    if (isStreaming) {
      console.warn('[chat] 当前还在流中,已忽略');
      return;
    }

    // 1. push user 消息
    const userMsg = makeMsg('user', query, { image_url: userImageUrl ?? undefined });
    // 2. 占位 assistant 消息(content 用 pendingContent 滚动覆盖)
    const assistantId = crypto.randomUUID();
    set((s) => ({
      messages: [
        ...s.messages,
        userMsg,
        { id: assistantId, role: 'assistant', content: '', created_at: Date.now(), streaming: true },
      ],
      isStreaming: true,
      thoughtSteps: [],
      pendingContent: '',
      pendingCitations: [],
    }));

    activeController?.abort();
    activeController = new AbortController();

    try {
      for await (const ev of chatApi.stream(
        { session_id: sessionId, query, image_object_key: imageObjectKey },
        activeController.signal,
      )) {
        applyEvent(ev, assistantId, set, get);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : '未知错误';
      // 把错误也塞到 assistant 消息里,让用户看见
      set((s) => ({
        messages: s.messages.map((m) =>
          m.id === assistantId ? { ...m, content: m.content || `请求失败:${msg}` } : m,
        ),
      }));
    } finally {
      // 收尾:落定 assistant 消息内容 + 引用 + 关掉 streaming 标记
      set((s) => ({
        messages: s.messages.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                content: s.pendingContent || m.content,
                citations: s.pendingCitations.length ? s.pendingCitations : m.citations,
                streaming: false,
              }
            : m,
        ),
        isStreaming: false,
      }));
      activeController = null;
    }
  },

  abort() {
    activeController?.abort();
    activeController = null;
    set({ isStreaming: false });
  },

  resetSession() {
    if (typeof window !== 'undefined') {
      const sid = crypto.randomUUID();
      localStorage.setItem(SESSION_KEY, sid);
      set({ sessionId: sid, messages: [], thoughtSteps: [], pendingContent: '', pendingCitations: [] });
    }
  },

  async switchSession(sessionId) {
    if (typeof window !== 'undefined') {
      localStorage.setItem(SESSION_KEY, sessionId);
    }
    activeController?.abort();
    activeController = null;
    set({
      sessionId,
      messages: [],
      thoughtSteps: [],
      pendingContent: '',
      pendingCitations: [],
      isStreaming: false,
    });
    try {
      const items = await chatApi.getMessages(sessionId);
      const msgs: ChatMessage[] = items.map((m) => ({
        id: `srv-${m.id}`,
        role: m.role,
        content: m.content,
        image_url: assetUrl(m.image_url) ?? undefined,
        created_at: m.created_at ? Date.parse(m.created_at) : Date.now(),
      }));
      set({ messages: msgs });
    } catch (err) {
      console.warn('[chat] switchSession 拉历史失败', err);
    }
  },

  async loadHistoryForCurrent() {
    const sid = get().sessionId;
    if (!sid) return;
    try {
      const items = await chatApi.getMessages(sid);
      if (items.length === 0) return; // 新 session 不覆盖本地消息
      const msgs: ChatMessage[] = items.map((m) => ({
        id: `srv-${m.id}`,
        role: m.role,
        content: m.content,
        image_url: assetUrl(m.image_url) ?? undefined,
        created_at: m.created_at ? Date.parse(m.created_at) : Date.now(),
      }));
      set({ messages: msgs });
    } catch {
      // 404 当前 session 还没入库;401 未登录 — 都静默
    }
  },

  toggleFloating(open) {
    set((s) => ({ floatingOpen: typeof open === 'boolean' ? open : !s.floatingOpen }));
  },
}));

// ============= 事件分发 =============
type SetFn = (
  partial:
    | Partial<ChatState & ChatActions>
    | ((s: ChatState & ChatActions) => Partial<ChatState & ChatActions>),
) => void;
type GetFn = () => ChatState & ChatActions;

function applyEvent(ev: AgentEvent, assistantId: string, set: SetFn, get: GetFn) {
  switch (ev.type) {
    case 'state_change': {
      // 标记前一个步骤为 done,推入新步骤为 running
      set((s) => {
        const steps = s.thoughtSteps.map((step) =>
          step.status === 'running' ? { ...step, status: 'done' as const, endedAt: Date.now() } : step,
        );
        // 同一 state 不重复入栈
        if (!steps.some((x) => x.state === ev.state)) {
          steps.push({ state: ev.state, status: 'running', startedAt: Date.now() });
        }
        return { thoughtSteps: steps };
      });
      break;
    }
    case 'tool_output': {
      // retrieve / rerank 工具吐出商品候选,先缓存
      if (ev.data?.products?.length) {
        set((s) => ({
          pendingCitations: dedupCitations([...s.pendingCitations, ...ev.data.products]),
        }));
      }
      break;
    }
    case 'token': {
      set((s) => {
        const newContent = s.pendingContent + ev.data;
        return {
          pendingContent: newContent,
          messages: s.messages.map((m) => (m.id === assistantId ? { ...m, content: newContent } : m)),
        };
      });
      break;
    }
    case 'citations': {
      if (Array.isArray(ev.data) && ev.data.length) {
        set((s) => ({ pendingCitations: dedupCitations([...s.pendingCitations, ...ev.data]) }));
      }
      break;
    }
    case 'done': {
      const final = ev.data;
      const citations = final.citations ?? get().pendingCitations;
      const webSources = final.web_sources;
      set((s) => ({
        messages: s.messages.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                content: final.answer || s.pendingContent || m.content,
                citations,
                web_sources: webSources && webSources.length > 0 ? webSources : undefined,
              }
            : m,
        ),
        // 标记所有 running 步骤完成
        thoughtSteps: s.thoughtSteps.map((step) =>
          step.status === 'running' ? { ...step, status: 'done', endedAt: Date.now() } : step,
        ),
      }));
      break;
    }
    case 'error': {
      const msg = ev.data?.msg || '后端返回错误';
      set((s) => ({
        messages: s.messages.map((m) =>
          m.id === assistantId ? { ...m, content: m.content || `⚠️ ${msg}` } : m,
        ),
      }));
      break;
    }
  }
}

function dedupCitations(list: ProductCard[]): ProductCard[] {
  const seen = new Set<number>();
  const out: ProductCard[] = [];
  for (const c of list) {
    if (!seen.has(c.product_id)) {
      seen.add(c.product_id);
      out.push(c);
    }
  }
  return out;
}
