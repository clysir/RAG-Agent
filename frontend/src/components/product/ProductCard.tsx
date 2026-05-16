/**
 * 商品卡片 —— 列表 / 网格里用。
 */

'use client';

import { Card, Image, Rate, Space, Tag, Typography } from 'antd';
import Link from 'next/link';
import { assetUrl } from '../../lib/asset';
import type { ProductOut } from '../../lib/types';

const { Text } = Typography;

export function ProductCard({ product }: { product: ProductOut }) {
  const fallback = '/img-placeholder.svg';
  const cover = assetUrl(product.image_url) || fallback;
  return (
    <Link href={`/products/${product.id}`} style={{ display: 'block' }}>
      <Card
        hoverable
        cover={
          <div
            style={{
              aspectRatio: '1 / 1',
              background: '#fafafa',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              overflow: 'hidden',
            }}
          >
            <Image
              src={cover}
              alt={product.title}
              preview={false}
              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              fallback={fallback}
            />
          </div>
        }
        styles={{ body: { padding: 12 } }}
        style={{ borderRadius: 12, overflow: 'hidden' }}
      >
        <Text
          style={{
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            fontSize: 13,
            lineHeight: 1.4,
            minHeight: 36,
          }}
        >
          {product.title}
        </Text>
        <Space size={6} style={{ marginTop: 8, width: '100%', justifyContent: 'space-between' }}>
          <Text type="danger" strong style={{ fontSize: 16 }}>
            {typeof product.price === 'number' ? `¥${product.price.toFixed(0)}` : '—'}
          </Text>
          {product.brand && (
            <Tag bordered={false} color="default" style={{ marginRight: 0 }}>
              {product.brand}
            </Tag>
          )}
        </Space>
        {(product.rating || product.review_count) && (
          <Space size={4} style={{ marginTop: 4, fontSize: 12, color: '#8c8c8c' }}>
            <Rate disabled allowHalf value={product.rating ?? 0} style={{ fontSize: 12 }} />
            <span>({product.review_count ?? 0})</span>
          </Space>
        )}
      </Card>
    </Link>
  );
}
