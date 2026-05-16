/**
 * /chat —— POST + FormData,返回 SSE 流。
 *
 * 走 apiRequestRaw 拿到 Response,再交给 streamSSE 解析事件。
 * 调用方:
 *   for await (const ev of chatApi.stream({ session_id, query })) {
 *     if (ev.type === 'token') ...
 *   }
 *
 * 历史侧栏接口:
 *   - listSessions: GET /chat/sessions
 *   - getMessages:  GET /chat/sessions/{id}/messages
 *   - deleteSession: DELETE /chat/sessions/{id}
 */

import { apiDelete, apiGet, apiRequestRaw } from './client';
import { streamSSE } from '../sse';
import type { AgentEvent, MessageOut, SessionBrief } from '../types';

export interface ChatRequest {
  session_id: string;
  query: string;
  image_object_key?: string;
}

export const chatApi = {
  /**
   * 发起一轮聊天。返回 AsyncGenerator,逐事件 yield。
   * @param signal AbortSignal,可以用来中途停掉(用户点"停止")
   */
  async *stream(req: ChatRequest, signal?: AbortSignal): AsyncGenerator<AgentEvent> {
    const form = new FormData();
    form.append('session_id', req.session_id);
    form.append('query', req.query);
    if (req.image_object_key) form.append('image_object_key', req.image_object_key);

    const res = await apiRequestRaw('/chat', {
      method: 'POST',
      form,
      signal,
    });
    yield* streamSSE(res);
  },

  /** 列出当前登录用户的全部会话。匿名调用会拿到 401。 */
  listSessions() {
    return apiGet<SessionBrief[]>('/chat/sessions');
  },

  /** 拉取指定会话的全部消息(校验所有权)。 */
  getMessages(sessionId: string) {
    return apiGet<MessageOut[]>(`/chat/sessions/${encodeURIComponent(sessionId)}/messages`);
  },

  /** 删除会话(连同消息一起)。 */
  deleteSession(sessionId: string) {
    return apiDelete<{ deleted: boolean; session_id: string }>(
      `/chat/sessions/${encodeURIComponent(sessionId)}`,
    );
  },
};
