/**
 * 认证全局状态:
 *   - token / 当前用户
 *   - login / logout 动作
 *   - 启动时自动 /auth/me 回灌 user
 *
 * 注:不写 persist 中间件,token 在 authStorage 里 + user 启动 fetch,
 * 是为了避免 token 已过期但 store 里还留 user 信息这种割裂状态。
 */

'use client';

import { create } from 'zustand';
import { authApi } from '../lib/api/auth';
import { ApiError } from '../lib/api/client';
import { authStorage } from '../lib/auth-storage';
import type { CurrentUser, TokenResponse } from '../lib/types';

interface AuthState {
  user: CurrentUser | null;
  /** 是否已经走过一次 /auth/me 探测 —— 防止初始化时闪烁 */
  hydrated: boolean;
  /** 后端拉取中 */
  loading: boolean;
}

interface AuthActions {
  /** 应用启动时调:从 localStorage 拿 token,有就 /auth/me 把 user 灌回来 */
  hydrate: () => Promise<void>;
  /** 拿到 token 后写入 */
  applyToken: (t: TokenResponse) => Promise<void>;
  logout: () => void;
}

export const useAuthStore = create<AuthState & AuthActions>((set) => ({
  user: null,
  hydrated: false,
  loading: false,

  async hydrate() {
    const token = authStorage.get();
    if (!token) {
      set({ hydrated: true });
      return;
    }
    set({ loading: true });
    try {
      const user = await authApi.me();
      set({ user, loading: false, hydrated: true });
    } catch (err) {
      // 401 已经在 client 里清了 token,这里只复位状态
      if (!(err instanceof ApiError)) console.warn('[auth] hydrate error', err);
      set({ user: null, loading: false, hydrated: true });
    }
  },

  async applyToken(t) {
    authStorage.set(t.access_token, t.expires_in);
    set({ loading: true });
    try {
      const user = await authApi.me();
      set({ user, loading: false, hydrated: true });
    } catch {
      authStorage.clear();
      set({ user: null, loading: false, hydrated: true });
    }
  },

  logout() {
    authStorage.clear();
    set({ user: null });
  },
}));
