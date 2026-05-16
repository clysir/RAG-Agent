/**
 * SSE 解析器:后端用 sse-starlette 输出 "data: {...}\n\n" 块。
 *
 * 因为 `/chat` 是 POST + FormData,EventSource API 不支持(只支持 GET),
 * 所以走 fetch + ReadableStream + 手写 line 解析。
 */

import type { AgentEvent } from './types';

type SepHit = { idx: number; len: number };

function findSeparator(buf: string): SepHit | null {
  const i1 = buf.indexOf('\n\n');
  const i2 = buf.indexOf('\r\n\r\n');
  if (i1 === -1 && i2 === -1) return null;
  if (i1 === -1) return { idx: i2, len: 4 };
  if (i2 === -1) return { idx: i1, len: 2 };
  return i1 < i2 ? { idx: i1, len: 2 } : { idx: i2, len: 4 };
}

function parseBlock(block: string): AgentEvent | null {
  // sse-starlette 默认只用 data: 单行;event: / id: / retry: 不关心。
  const lines = block.split(/\r?\n/);
  const dataLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (dataLines.length === 0) return null;
  const raw = dataLines.join('\n');
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AgentEvent;
  } catch {
    // 心跳包 / 非 JSON 直接吞
    return null;
  }
}

/**
 * 把 fetch 的 SSE Response 转成 AgentEvent 异步迭代器。
 * 调用方在 for await 里逐事件处理(state_change / token / done 等)。
 */
export async function* streamSSE(res: Response): AsyncGenerator<AgentEvent> {
  if (!res.body) throw new Error('SSE Response 没有 body');
  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let hit = findSeparator(buffer);
      while (hit) {
        const block = buffer.slice(0, hit.idx);
        buffer = buffer.slice(hit.idx + hit.len);
        const event = parseBlock(block);
        if (event) yield event;
        hit = findSeparator(buffer);
      }
    }
    // 流结束,残留 buffer 也尝试解一下(后端理论上会补 \n\n,但保险)
    if (buffer.trim()) {
      const event = parseBlock(buffer);
      if (event) yield event;
    }
  } finally {
    reader.releaseLock();
  }
}
