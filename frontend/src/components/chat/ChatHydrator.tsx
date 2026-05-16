/**
 * 同 AuthHydrator,首次挂载初始化 chatStore 的 sessionId(从 localStorage 拿或新生成)。
 */

'use client';

import { useEffect } from 'react';
import { useChatStore } from '../../store/chatStore';

export function ChatHydrator() {
  useEffect(() => {
    useChatStore.getState().hydrate();
  }, []);
  return null;
}
