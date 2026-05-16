/**
 * 可复用的聊天主体。
 *   - 悬浮气泡:`<ChatBody compact />` 紧凑布局
 *   - 完整页:`<ChatBody />` 大版心
 *
 * 内部用 AntD X 的 Bubble / Sender / Welcome / Prompts。
 *
 * 注:这里手动 map 渲染 <Bubble>(而不是 Bubble.List)的原因是 v2 的
 * BubbleItemType 联合体在直接给 placement/avatar 时和 role 模式分支识别有歧义,
 * 逐个渲染反而类型干净。
 */

'use client';

import { Bubble, Prompts, Sender, Welcome } from '@ant-design/x';
import { App as AntApp, Avatar, Button, Image, Space, Tooltip, Upload, type UploadProps } from 'antd';
import {
  PaperClipOutlined,
  PictureOutlined,
  RobotOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { useEffect, useRef, useState } from 'react';
import { uploadApi } from '../../lib/api/upload';
import { useChatStore } from '../../store/chatStore';
import { CitationCards } from './CitationCards';
import { ThoughtChainPanel } from './ThoughtChainPanel';
import type { ChatMessage } from '../../lib/types';

type CustomUploadArg = Parameters<NonNullable<UploadProps['customRequest']>>[0];

interface Props {
  compact?: boolean;
  /** 完整页可以传 false 去掉欢迎区(已经在页头展示) */
  showWelcome?: boolean;
}

const SUGGESTED_PROMPTS = [
  { key: 'p1', label: '推荐几款雪纺连衣裙' },
  { key: 'p2', label: '500 元以内的通勤双肩包' },
  { key: 'p3', label: '有没有适合敏感肌的洁面' },
  { key: 'p4', label: '帮我看看这张图里的衣服', icon: <PictureOutlined /> },
];

export function ChatBody({ compact, showWelcome = true }: Props) {
  const { message } = AntApp.useApp();
  const messages = useChatStore((s) => s.messages);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const send = useChatStore((s) => s.send);
  const abort = useChatStore((s) => s.abort);
  const thoughtSteps = useChatStore((s) => s.thoughtSteps);

  const [input, setInput] = useState('');
  const [pendingImage, setPendingImage] = useState<{ key: string; url: string } | null>(null);
  const [uploading, setUploading] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);

  // 新消息进来 / 流式推进时自动滚到底
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, thoughtSteps, isStreaming]);

  const onUpload = async (opt: CustomUploadArg) => {
    const file = opt.file as File;
    if (!file) return;
    setUploading(true);
    try {
      const res = await uploadApi.image(file);
      setPendingImage({ key: res.object_key, url: res.url });
      opt.onSuccess?.(res);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '上传失败';
      message.error(msg);
      opt.onError?.(err as Error);
    } finally {
      setUploading(false);
    }
  };

  const onSubmit = (value: string) => {
    const text = value.trim();
    if (!text && !pendingImage) return;
    // 把已上传图片的 URL 一起传给 store 以便用户气泡里展示
    void send(text || '帮我分析这张图', pendingImage?.key, pendingImage?.url);
    setInput('');
    setPendingImage(null);
  };

  const isEmpty = messages.length === 0;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: 0,
        background: compact ? '#fff' : 'transparent',
      }}
    >
      {/* 消息区 + 思考链 */}
      <div
        ref={scrollRef}
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: compact ? '12px 16px' : '24px 0',
          minHeight: 0,
        }}
      >
        {isEmpty && showWelcome ? (
          <>
            <Welcome
              variant="borderless"
              icon={<RobotOutlined style={{ fontSize: 28, color: '#1677ff' }} />}
              title="你好,我是 RAG-Agent 导购"
              description="问我「想要什么」「适合什么场景」「有没有图片」,我会帮你在 2000+ 真实商品里精选推荐。"
            />
            <div style={{ marginTop: 16 }}>
              <Prompts
                title="试试这些"
                wrap
                items={SUGGESTED_PROMPTS}
                onItemClick={(info) => onSubmit(info.data.label as string)}
              />
            </div>
          </>
        ) : (
          <>
            {(isStreaming || thoughtSteps.length > 0) && <ThoughtChainPanel />}
            <Space orientation="vertical" size={16} style={{ width: '100%' }}>
              {messages.map((m) => (
                <MessageBubble key={m.id} message={m} compact={compact} />
              ))}
            </Space>
          </>
        )}
      </div>

      {/* 输入区 */}
      <div style={{ padding: compact ? '8px 12px 12px' : '12px 0 0' }}>
        {pendingImage && (
          <div
            style={{
              padding: 8,
              marginBottom: 8,
              background: '#fafafa',
              borderRadius: 8,
              display: 'flex',
              alignItems: 'center',
              gap: 12,
            }}
          >
            <Image
              src={pendingImage.url}
              width={48}
              height={48}
              style={{ borderRadius: 6, objectFit: 'cover' }}
              preview={false}
            />
            <span style={{ flex: 1, fontSize: 12, color: '#595959' }}>已附图,发送时一起上传</span>
            <Button size="small" type="text" onClick={() => setPendingImage(null)}>
              移除
            </Button>
          </div>
        )}
        <Sender
          value={input}
          onChange={setInput}
          onSubmit={onSubmit}
          onCancel={abort}
          loading={isStreaming}
          placeholder="输入你的问题,或上传图片让我帮你识图找货"
          autoSize={{ minRows: 1, maxRows: 4 }}
          prefix={
            <Upload
              accept="image/*"
              showUploadList={false}
              customRequest={onUpload}
              disabled={uploading || isStreaming}
            >
              <Tooltip title="上传图片">
                <Button
                  type="text"
                  icon={<PaperClipOutlined />}
                  loading={uploading}
                  disabled={isStreaming}
                />
              </Tooltip>
            </Upload>
          }
        />
      </div>
    </div>
  );
}

function MessageBubble({ message: m, compact }: { message: ChatMessage; compact?: boolean }) {
  if (m.role === 'user') {
    return (
      <Bubble
        placement="end"
        avatar={<Avatar icon={<UserOutlined />} style={{ background: '#87d068' }} />}
        content={
          m.image_url ? (
            <Space orientation="vertical" size={6}>
              <Image
                src={m.image_url}
                width={compact ? 120 : 180}
                style={{ borderRadius: 8 }}
                preview={{ mask: '点击查看大图' }}
              />
              {m.content && <span>{m.content}</span>}
            </Space>
          ) : (
            <span>{m.content}</span>
          )
        }
      />
    );
  }
  // assistant
  return (
    <Bubble
      placement="start"
      avatar={<Avatar icon={<RobotOutlined />} style={{ background: '#1677ff' }} />}
      content={m.content || ' '}
      loading={m.content === '' && m.streaming === true}
      typing={m.streaming ? true : undefined}
      footer={
        m.citations && m.citations.length > 0 ? (
          <CitationCards citations={m.citations} compact={compact} />
        ) : undefined
      }
    />
  );
}
