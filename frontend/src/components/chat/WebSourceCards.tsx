/**
 * 联网搜索来源卡片 —— WEB_FALLBACK 状态把外部来源透传过来,在 assistant 消息底部展示。
 *
 * 跟 CitationCards(店内商品卡)视觉上明显区分:
 *   - 不用商品图(网搜没图)
 *   - 主体是标题 + 摘要 + 域名 + 外链
 *   - 标记上"网络搜索"图标,提醒用户"这不是本店商品"
 */

'use client';

import { GlobalOutlined, LinkOutlined } from '@ant-design/icons';
import { Card, Space, Tag, Typography } from 'antd';
import type { WebSource } from '../../lib/types';

const { Text } = Typography;

interface Props {
  sources: WebSource[];
  compact?: boolean;
}

export function WebSourceCards({ sources, compact }: Props) {
  if (!sources || sources.length === 0) return null;

  return (
    <div style={{ display: 'grid', gap: 8, marginTop: 10 }}>
      <Space size={6} style={{ fontSize: 12, color: '#fa8c16' }}>
        <GlobalOutlined />
        <Text style={{ fontSize: 12, color: '#fa8c16' }}>
          网络搜索结果 · {sources.length} 条(非本店商品)
        </Text>
      </Space>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: compact ? '1fr' : 'repeat(auto-fill, minmax(280px, 1fr))',
          gap: 8,
        }}
      >
        {sources.map((s, idx) => (
          <Card
            key={`${s.url}-${idx}`}
            size="small"
            hoverable
            styles={{ body: { padding: 10 } }}
            style={{ borderRadius: 10, borderLeft: '3px solid #fa8c16' }}
            onClick={() => window.open(s.url, '_blank', 'noopener,noreferrer')}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6 }}>
              <Text
                style={{
                  flex: 1,
                  fontSize: 13,
                  fontWeight: 500,
                  lineHeight: 1.4,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                }}
              >
                {s.title}
              </Text>
              <LinkOutlined style={{ color: '#bfbfbf', fontSize: 12, marginTop: 3 }} />
            </div>
            {s.snippet && (
              <Text
                type="secondary"
                style={{
                  fontSize: 12,
                  marginTop: 4,
                  display: '-webkit-box',
                  WebkitLineClamp: compact ? 2 : 3,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                }}
              >
                {s.snippet}
              </Text>
            )}
            <Space size={6} style={{ marginTop: 6 }}>
              <Tag color="orange" bordered={false} style={{ fontSize: 11, marginRight: 0 }}>
                {s.source || '外部来源'}
              </Tag>
              {s.publish_date && (
                <Text type="secondary" style={{ fontSize: 11 }}>
                  {s.publish_date}
                </Text>
              )}
            </Space>
          </Card>
        ))}
      </div>
    </div>
  );
}
