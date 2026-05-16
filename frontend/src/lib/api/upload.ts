/**
 * /upload/image —— multipart/form-data 上传图片,返回 object_key 给后续聊天 / 商品用。
 *
 * url 返回的是 storage.presign_url 的结果,local_fs 模式是相对路径 "/static/...",
 * 这里在 API 边界统一打到后端绝对 URL,UI 层就不用每个都包一次。
 */

import { apiPost } from './client';
import { assetUrl } from '../asset';
import type { UploadResponse } from '../types';

export const uploadApi = {
  /** 上传图片;支持 jpg / png / webp / gif,≤ 10MB */
  async image(file: File): Promise<UploadResponse> {
    const form = new FormData();
    form.append('file', file);
    const res = await apiPost<UploadResponse>('/upload/image', { form });
    return { ...res, url: assetUrl(res.url) ?? res.url };
  },
};
