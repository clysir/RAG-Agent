/**
 * /merchant/* —— 商家提交商品 + 看自己提交列表(最小 UI)。
 */

import { apiGet, apiPost } from './client';
import type { MerchantSubmitRequest, SubmissionBrief } from '../types';

export const merchantApi = {
  submit(body: MerchantSubmitRequest) {
    return apiPost<SubmissionBrief>('/merchant/products', { json: body });
  },

  mySubmissions() {
    return apiGet<SubmissionBrief[]>('/merchant/products');
  },
};
