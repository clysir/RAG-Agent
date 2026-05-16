/**
 * 商品网格 + 简单筛选 + 分页(用 TanStack Query + 后端 GET /products)。
 */

'use client';

import { Button, Empty, Input, Pagination, Select, Skeleton, Space, theme, Typography } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { productsApi } from '../../lib/api/products';
import { ProductCard } from './ProductCard';
import type { ProductListParams } from '../../lib/types';

const { Title, Text } = Typography;

const DEFAULT_PAGE_SIZE = 24;

export function ProductGrid() {
  const { token } = theme.useToken();
  const [params, setParams] = useState<ProductListParams>({ page: 1, page_size: DEFAULT_PAGE_SIZE });
  const [searchInput, setSearchInput] = useState('');

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['products', params],
    queryFn: () => productsApi.list(params),
  });

  const onSearch = () => setParams((p) => ({ ...p, q: searchInput || undefined, page: 1 }));

  return (
    <div style={{ padding: '24px 16px', maxWidth: 1280, margin: '0 auto' }}>
      <Space
        style={{
          width: '100%',
          marginBottom: 16,
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 12,
        }}
      >
        <div>
          <Title level={4} style={{ margin: 0 }}>
            商品库
          </Title>
          <Text type="secondary">2000+ 真实电商 SKU,Agent 实时检索可用</Text>
        </div>
        <Space size={8} wrap>
          <Input
            placeholder="搜索关键词(可选)"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onPressEnter={onSearch}
            allowClear
            prefix={<SearchOutlined style={{ color: token.colorTextTertiary }} />}
            style={{ width: 220 }}
          />
          <Select
            placeholder="价格区间"
            allowClear
            style={{ width: 130 }}
            options={[
              { value: '0-100', label: '< ¥100' },
              { value: '100-300', label: '¥100-300' },
              { value: '300-500', label: '¥300-500' },
              { value: '500-1000', label: '¥500-1000' },
              { value: '1000-', label: '> ¥1000' },
            ]}
            onChange={(val: string | undefined) => {
              if (!val) {
                setParams((p) => ({ ...p, min_price: undefined, max_price: undefined, page: 1 }));
                return;
              }
              const [lo, hi] = val.split('-');
              setParams((p) => ({
                ...p,
                min_price: lo ? Number(lo) : undefined,
                max_price: hi ? Number(hi) : undefined,
                page: 1,
              }));
            }}
          />
          <Button onClick={onSearch} type="primary">
            搜索
          </Button>
        </Space>
      </Space>

      {isLoading && <SkeletonGrid />}

      {isError && (
        <Empty description="接口报错,请检查后端 8000 端口是否启动">
          <Button onClick={() => refetch()}>重试</Button>
        </Empty>
      )}

      {!isLoading && !isError && (
        <>
          {data && data.items.length > 0 ? (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
                gap: 16,
              }}
            >
              {data.items.map((p) => (
                <ProductCard key={p.id} product={p} />
              ))}
            </div>
          ) : (
            <Empty description="没找到相关商品" />
          )}

          {data && data.total > DEFAULT_PAGE_SIZE && (
            <div style={{ display: 'flex', justifyContent: 'center', marginTop: 24 }}>
              <Pagination
                current={data.page}
                pageSize={data.page_size}
                total={data.total}
                onChange={(page) => setParams((p) => ({ ...p, page }))}
                showSizeChanger={false}
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}

function SkeletonGrid() {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
        gap: 16,
      }}
    >
      {Array.from({ length: 12 }).map((_, i) => (
        <div key={i} style={{ background: '#fff', borderRadius: 12, padding: 12 }}>
          <Skeleton.Image active style={{ width: '100%', height: 180, borderRadius: 8 }} />
          <Skeleton active paragraph={{ rows: 1 }} style={{ marginTop: 12 }} />
        </div>
      ))}
    </div>
  );
}
