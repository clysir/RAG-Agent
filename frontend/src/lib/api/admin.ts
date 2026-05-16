/**
 * /admin/* —— 管理员审核商品提交 + 用户封禁(最小 UI)。
 */

import { apiGet, apiPost } from './client';
import type { SubmissionBrief, SubmissionStatus } from '../types';

export const adminApi = {
  submissions(status?: SubmissionStatus) {
    return apiGet<SubmissionBrief[]>('/admin/submissions', {
      query: { submission_status: status },
    });
  },

  approve(id: number) {
    return apiPost<{ product_id: number; submission_id: number }>(
      `/admin/submissions/${id}/approve`,
      {},
    );
  },

  reject(id: number, reason: string) {
    return apiPost<{ submission_id: number }>(`/admin/submissions/${id}/reject`, {
      json: { reason },
    });
  },

  banUser(userId: number, reason?: string) {
    return apiPost<{ user_id: number; status: string }>(`/admin/users/${userId}/ban`, {
      json: reason ? { reason } : undefined,
    });
  },

  unbanUser(userId: number) {
    return apiPost<{ user_id: number; status: string }>(`/admin/users/${userId}/unban`, {});
  },
};
