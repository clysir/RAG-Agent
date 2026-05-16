/**
 * 首页:Hero 介绍 + 商品网格。
 *
 * Hero 是 marketing 区,告诉用户这是个 AI 导购,引导他们要么浏览商品,要么聊天。
 */

'use client';

import { MessageOutlined, RobotOutlined } from '@ant-design/icons';
import { Button, Space, theme, Typography } from 'antd';
import Link from 'next/link';
import { ProductGrid } from '../components/product/ProductGrid';
import { useChatStore } from '../store/chatStore';

const { Title, Text } = Typography;

export default function HomePage() {
  const { token } = theme.useToken();
  const toggleFloating = useChatStore((s) => s.toggleFloating);

  return (
    <div>
      <section
        style={{
          background: `linear-gradient(135deg, ${token.colorPrimary} 0%, #6c5ce7 100%)`,
          color: '#fff',
          padding: '40px 16px 56px',
        }}
      >
        <div style={{ maxWidth: 1280, margin: '0 auto' }}>
          <Space size={12} style={{ marginBottom: 12 }}>
            <RobotOutlined style={{ fontSize: 28 }} />
            <Title level={3} style={{ color: '#fff', margin: 0 }}>
              RAG-Agent · 多模态智能导购
            </Title>
          </Space>
          <Text style={{ color: 'rgba(255,255,255,0.9)', fontSize: 15, display: 'block' }}>
            自然语言或图片提问 → Agent 自研 8 状态机调度 → 多路召回 + 跨模态精排 → 流式带引用回答。
          </Text>
          <Space style={{ marginTop: 20 }} size={12} wrap>
            <Link href="/chat">
              <Button
                size="large"
                type="primary"
                style={{ background: '#fff', color: token.colorPrimary }}
                icon={<MessageOutlined />}
              >
                开始聊天
              </Button>
            </Link>
            <Button
              size="large"
              ghost
              icon={<MessageOutlined />}
              onClick={() => toggleFloating(true)}
              style={{ borderColor: 'rgba(255,255,255,0.6)', color: '#fff' }}
            >
              浮窗试用
            </Button>
          </Space>
        </div>
      </section>

      <ProductGrid />
    </div>
  );
}
