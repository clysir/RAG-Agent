/**
 * 引用商品卡:把 assistant 消息的 citations 渲染成可点击的小卡片列表。
 * 用户点卡片跳商品详情。
 */

'use client';

import { Card, Image, Space, Tag, Typography } from 'antd';
import Link from 'next/link';
import { assetUrl } from '../../lib/asset';
import type { ProductCard } from '../../lib/types';

const { Text } = Typography;

interface Props {
  citations: ProductCard[];
  /** 紧凑模式(悬浮聊天里用),false 是完整页 */
  compact?: boolean;
}

export function CitationCards({ citations, compact }: Props) {
  if (!citations || citations.length === 0) {
    return null;
  }

  const cardSize: number = compact ? 64 : 88;

  return (
    <div style={{ display: 'grid', gap: 8, marginTop: 10 }}>
      <Text type="secondary" style={{ fontSize: 12 }}>
        相关商品 · {citations.length} 个
      </Text>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: compact ? '1fr' : 'repeat(auto-fill, minmax(260px, 1fr))',
          gap: 8,
        }}
      >
        {citations.map((c) => (
          <Link href={`/products/${c.product_id}`} key={c.product_id}>
            <Card
              size="small"
              hoverable
              styles={{ body: { padding: 8 } }}
              style={{ borderRadius: 10 }}
            >
              <Space size={10} align="start">
                {c.image_url ? (
                  <Image
                    src={assetUrl(c.image_url)}
                    alt={c.title}
                    width={cardSize}
                    height={cardSize}
                    style={{ borderRadius: 8, objectFit: 'cover' }}
                    preview={false}
                    fallback="/img-placeholder.svg"
                  />
                ) : (
                  <div
                    style={{
                      width: cardSize,
                      height: cardSize,
                      background: '#f0f0f0',
                      borderRadius: 8,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: '#bfbfbf',
                      fontSize: 12,
                    }}
                  >
                    无图
                  </div>
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <Text
                    style={{
                      fontWeight: 500,
                      fontSize: 13,
                      lineHeight: 1.4,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      display: '-webkit-box',
                      WebkitLineClamp: compact ? 1 : 2,
                      WebkitBoxOrient: 'vertical',
                    }}
                  >
                    {c.title}
                  </Text>
                  <Space size={6} style={{ marginTop: 4 }}>
                    {typeof c.price === 'number' && (
                      <Text type="danger" strong style={{ fontSize: 13 }}>
                        ¥{c.price.toFixed(0)}
                      </Text>
                    )}
                    <Tag color="blue" style={{ marginRight: 0 }}>
                      score {c.score.toFixed(2)}
                    </Tag>
                  </Space>
                  {c.snippet && !compact && (
                    <Text
                      type="secondary"
                      style={{
                        display: '-webkit-box',
                        WebkitLineClamp: 1,
                        WebkitBoxOrient: 'vertical',
                        overflow: 'hidden',
                        fontSize: 12,
                        marginTop: 4,
                      }}
                    >
                      {c.snippet}
                    </Text>
                  )}
                </div>
              </Space>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
