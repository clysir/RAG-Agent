/**
 * 商品详情页 /products/[id]
 *
 * 大图 + 标题 + 价 + 评分 + 描述。底部按钮"问 AI 导购关于这件商品" → 自动开浮窗发提问。
 */

'use client';

import { use } from 'react';
import { App as AntApp, Button, Card, Image, Rate, Skeleton, Space, Tag, theme, Typography } from 'antd';
import { MessageOutlined, ShopOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { productsApi } from '../../../lib/api/products';
import { assetUrl } from '../../../lib/asset';
import { useChatStore } from '../../../store/chatStore';

const { Title, Paragraph, Text } = Typography;

export default function ProductDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { message } = AntApp.useApp();
  const productId = Number(id);
  const { token } = theme.useToken();
  const send = useChatStore((s) => s.send);
  const toggleFloating = useChatStore((s) => s.toggleFloating);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['product', productId],
    queryFn: () => productsApi.detail(productId),
    enabled: Number.isFinite(productId),
  });

  const askAgent = async () => {
    if (!data) return;
    toggleFloating(true);
    // 给一点时间让 floating 展开
    await new Promise((r) => setTimeout(r, 200));
    void send(`帮我看看这件商品「${data.title}」,值得买吗?有没有同类更便宜的?`);
    message.success('已问 AI 导购,看右下角浮窗');
  };

  if (isLoading) {
    return (
      <div style={{ maxWidth: 1100, margin: '24px auto', padding: '0 16px' }}>
        <Skeleton active paragraph={{ rows: 6 }} />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div style={{ maxWidth: 1100, margin: '24px auto', padding: '24px 16px' }}>
        <Text type="danger">商品加载失败</Text>
        <br />
        <Link href="/">
          <Button>返回首页</Button>
        </Link>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 1100, margin: '24px auto', padding: '0 16px' }}>
      <Card style={{ borderRadius: 12 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 460px) 1fr', gap: 32 }}>
          <div
            style={{
              aspectRatio: '1 / 1',
              background: '#fafafa',
              borderRadius: 12,
              overflow: 'hidden',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Image
              src={assetUrl(data.image_url) || '/img-placeholder.svg'}
              alt={data.title}
              fallback="/img-placeholder.svg"
              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            />
          </div>
          <div>
            <Title level={3} style={{ marginTop: 0 }}>
              {data.title}
            </Title>
            <Space size={12} wrap>
              {data.brand && (
                <Tag icon={<ShopOutlined />} color="blue">
                  {data.brand}
                </Tag>
              )}
              {data.category && <Tag>{data.category}</Tag>}
            </Space>
            <div style={{ marginTop: 16, display: 'flex', alignItems: 'baseline', gap: 12 }}>
              <Text type="danger" style={{ fontSize: 28, fontWeight: 600 }}>
                ¥{typeof data.price === 'number' ? data.price.toFixed(0) : '—'}
              </Text>
              {data.rating !== undefined && data.rating !== null && (
                <Space size={4}>
                  <Rate disabled allowHalf value={data.rating} style={{ fontSize: 14 }} />
                  <Text type="secondary">({data.review_count ?? 0})</Text>
                </Space>
              )}
            </div>
            {data.description && (
              <Paragraph
                style={{ marginTop: 16, color: token.colorTextSecondary, whiteSpace: 'pre-wrap' }}
              >
                {data.description}
              </Paragraph>
            )}
            <Space size={12} style={{ marginTop: 24 }}>
              <Button type="primary" size="large" icon={<MessageOutlined />} onClick={askAgent}>
                问 AI 导购
              </Button>
              <Link href="/">
                <Button size="large">继续逛</Button>
              </Link>
            </Space>
          </div>
        </div>
      </Card>
    </div>
  );
}
