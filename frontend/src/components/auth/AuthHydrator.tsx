/**
 * 首次挂载触发 authStore.hydrate(),把 localStorage 里的 token 灌成 user。
 * 单独抽出来是因为 hydrate 要 useEffect,要在 client component 里执行。
 */

'use client';

import { useEffect } from 'react';
import { useAuthStore } from '../../store/authStore';

export function AuthHydrator() {
  useEffect(() => {
    useAuthStore.getState().hydrate();
  }, []);
  return null;
}
