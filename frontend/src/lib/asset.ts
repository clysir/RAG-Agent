/**
 * 静态资源 URL 兜底处理。
 *
 * 后端 local_fs storage 的 presign_url 返回 "/static/..." 相对路径,
 * 浏览器会按当前 origin(3000)解析,导致 404。
 * 这里统一把它们打到 NEXT_PUBLIC_API_BASE_URL(8000)。
 *
 * 已经是绝对 URL(http/https/data:)直接放行。
 */

import { BASE_URL } from './api/client';

export function assetUrl(maybe: string | null | undefined): string | undefined {
  if (!maybe) return undefined;
  if (/^(https?:)?\/\//i.test(maybe) || maybe.startsWith('data:')) return maybe;
  if (maybe.startsWith('/')) return `${BASE_URL}${maybe}`;
  return `${BASE_URL}/${maybe}`;
}
