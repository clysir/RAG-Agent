/**
 * JWT token 在 localStorage 里的存取。本期不做 HttpOnly cookie。
 * 服务端组件碰不到 localStorage,所有需要 token 的地方都得是 client component。
 */

const KEY_TOKEN = 'rag_jwt';
const KEY_EXPIRES_AT = 'rag_jwt_exp';

export const authStorage = {
  get(): string | null {
    if (typeof window === 'undefined') return null;
    const token = localStorage.getItem(KEY_TOKEN);
    if (!token) return null;
    // 过期判断:简单查存的过期戳
    const expStr = localStorage.getItem(KEY_EXPIRES_AT);
    if (expStr) {
      const exp = Number(expStr);
      if (Number.isFinite(exp) && Date.now() > exp) {
        // 已过期,清掉,避免带着过期 token 撞后端
        this.clear();
        return null;
      }
    }
    return token;
  },

  set(token: string, expiresInSeconds: number) {
    if (typeof window === 'undefined') return;
    localStorage.setItem(KEY_TOKEN, token);
    const expiresAt = Date.now() + expiresInSeconds * 1000;
    localStorage.setItem(KEY_EXPIRES_AT, String(expiresAt));
  },

  clear() {
    if (typeof window === 'undefined') return;
    localStorage.removeItem(KEY_TOKEN);
    localStorage.removeItem(KEY_EXPIRES_AT);
  },
};
