/**
 * /memory/* —— 用户长期记忆管理(PIPL 合规 + 透明度)。
 */

import { apiDelete, apiGet, apiPost } from './client';
import type { FactType, MemoryList } from '../types';

export const memoryApi = {
  list(params: { limit?: number; fact_type?: FactType } = {}) {
    return apiGet<MemoryList>('/memory/', { query: { limit: params.limit, fact_type: params.fact_type } });
  },

  /** 列全部含失效(双时态审计用) */
  listAll(limit = 200) {
    return apiGet<MemoryList>('/memory/all', { query: { limit } });
  },

  /** 软删除一条:set valid_to=now() */
  remove(id: number) {
    return apiDelete<{ deleted: boolean; fact_id: number }>(`/memory/${id}`);
  },

  /** 一键忘记:所有当前事实 valid_to=now() */
  forgetAll() {
    return apiPost<{ invalidated: number }>('/memory/forget-all', {});
  },
};
