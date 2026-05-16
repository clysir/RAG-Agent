/**
 * /products 接口封装(公开,允许游客访问)。
 *
 * 注意:后端实际 GET /products 的字段名以 backend/app/api/products.py 为准,
 * 这里按 ProductListParams 传 query string,有不识别字段后端会忽略。
 */

import { apiGet } from './client';
import type { ProductListParams, ProductListResponse, ProductOut } from '../types';

export const productsApi = {
  list(params: ProductListParams = {}) {
    return apiGet<ProductListResponse>('/products', {
      query: {
        page: params.page,
        page_size: params.page_size,
        category: params.category,
        brand: params.brand,
        min_price: params.min_price,
        max_price: params.max_price,
        q: params.q,
      },
      skipAuth: true,
    });
  },

  detail(id: number) {
    return apiGet<ProductOut>(`/products/${id}`, { skipAuth: true });
  },

  categories() {
    // 后端若有 /products/categories 取分类列表;没有的话前端可以从 list() 自己 distinct
    return apiGet<string[]>('/products/categories', { skipAuth: true });
  },

  brands() {
    return apiGet<string[]>('/products/brands', { skipAuth: true });
  },
};
