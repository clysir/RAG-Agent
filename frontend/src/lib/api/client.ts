/**
 * 统一 HTTP 客户端:
 *   - 自动注入 Authorization: Bearer <jwt>
 *   - 自动解开 ApiResponse 壳,业务代码只拿 data
 *   - 401 → 清 token + 抛 ApiError
 *   - 非 0 code → 抛 ApiError(可以在 React Query / Form 里捕获)
 *
 * 用法:
 *   const user = await apiGet<CurrentUser>('/auth/me');
 *   const product = await apiPost<ProductOut>('/products', body);
 */

import { authStorage } from '../auth-storage';
import type { ApiResponse } from '../types';

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export class ApiError extends Error {
  code: number;
  status?: number;
  constructor(message: string, code: number, status?: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  /** application/json 时传 body 对象 */
  json?: unknown;
  /** multipart/form-data 时传 FormData */
  form?: FormData;
  /** application/x-www-form-urlencoded 时传 URLSearchParams(后端 /auth/login 用这种) */
  urlEncoded?: URLSearchParams;
  /** query string */
  query?: Record<string, string | number | undefined | null>;
  /** 跳过认证(注册 / 登录 / 公开商品) */
  skipAuth?: boolean;
  /** AbortSignal,给 SSE / 长任务取消用 */
  signal?: AbortSignal;
};

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = new URL(path.startsWith('http') ? path : `${BASE_URL}${path}`);
  if (query) {
    Object.entries(query).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') {
        url.searchParams.set(k, String(v));
      }
    });
  }
  return url.toString();
}

/**
 * 发请求并自动解 ApiResponse 壳。返回 data 字段。
 * 调用方拿到的就是业务数据,而不是 { code, message, data }。
 */
export async function apiRequest<T = unknown>(
  path: string,
  opts: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  if (!opts.skipAuth) {
    const token = authStorage.get();
    if (token) headers['Authorization'] = `Bearer ${token}`;
  }

  let body: BodyInit | undefined;
  if (opts.json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(opts.json);
  } else if (opts.form) {
    body = opts.form;
  } else if (opts.urlEncoded) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded';
    body = opts.urlEncoded.toString();
  }

  const res = await fetch(buildUrl(path, opts.query), {
    method: opts.method || (body ? 'POST' : 'GET'),
    headers,
    body,
    signal: opts.signal,
    credentials: 'omit',
  });

  if (res.status === 401) {
    authStorage.clear();
    throw new ApiError('未登录或登录已过期', 2001, 401);
  }

  if (!res.ok && res.status >= 500) {
    throw new ApiError(`服务端错误 (${res.status})`, 5000, res.status);
  }

  const json = (await res.json()) as ApiResponse<T>;
  if (json.code !== 0) {
    throw new ApiError(json.message || '业务错误', json.code, res.status);
  }
  return json.data as T;
}

export function apiGet<T>(path: string, opts: Omit<RequestOptions, 'method' | 'json' | 'form'> = {}) {
  return apiRequest<T>(path, { ...opts, method: 'GET' });
}

export function apiPost<T>(path: string, opts: Omit<RequestOptions, 'method'> = {}) {
  return apiRequest<T>(path, { ...opts, method: 'POST' });
}

export function apiDelete<T>(path: string, opts: Omit<RequestOptions, 'method'> = {}) {
  return apiRequest<T>(path, { ...opts, method: 'DELETE' });
}

/**
 * SSE / 流式专用:不解 ApiResponse 壳,直接拿到原始 Response。
 * 由调用方用 streamSSE 解。
 */
export async function apiRequestRaw(
  path: string,
  opts: RequestOptions = {},
): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'text/event-stream' };
  if (!opts.skipAuth) {
    const token = authStorage.get();
    if (token) headers['Authorization'] = `Bearer ${token}`;
  }
  let body: BodyInit | undefined;
  if (opts.json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(opts.json);
  } else if (opts.form) {
    body = opts.form;
  }
  const res = await fetch(buildUrl(path, opts.query), {
    method: opts.method || 'POST',
    headers,
    body,
    signal: opts.signal,
    credentials: 'omit',
  });
  if (res.status === 401) {
    authStorage.clear();
    throw new ApiError('未登录或登录已过期', 2001, 401);
  }
  if (!res.ok) {
    throw new ApiError(`SSE 流建立失败 (${res.status})`, res.status, res.status);
  }
  return res;
}

export { BASE_URL };
