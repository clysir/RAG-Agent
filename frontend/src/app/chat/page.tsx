/**
 * 完整聊天页 /chat
 *
 * 比悬浮气泡多:
 *   - 左侧"我的对话"历史栏(后端 GET /chat/sessions)— 未登录态隐藏
 *   - 主区头部有"新会话"按钮 + 思考链常驻
 *
 * 切换会话:点 sidebar 条目 → switchSession(id) → 拉 GET /messages 灌进 store
 * 新会话:resetSession() 生成新 UUID,messages 清零,后端在第一条消息时 lazy 建 row
 */

'use client';

import { useEffect } from 'react';
import { ClearOutlined, DeleteOutlined, MessageOutlined, PlusOutlined, RobotOutlined } from '@ant-design/icons';
import { App as AntApp, Button, Empty, Layout, Popconfirm, Skeleton, Space, Tooltip, Typography } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { chatApi } from '../../lib/api/chat';
import { useAuthStore } from '../../store/authStore';
import { useChatStore } from '../../store/chatStore';
import { ChatBody } from '../../components/chat/ChatBody';
import type { SessionBrief } from '../../lib/types';

const { Title, Text } = Typography;
const { Content, Sider } = Layout;

export default function ChatPage() {
  const { message } = AntApp.useApp();
  const user = useAuthStore((s) => s.user);
  const hydrated = useAuthStore((s) => s.hydrated);
  const sessionId = useChatStore((s) => s.sessionId);
  const resetSession = useChatStore((s) => s.resetSession);
  const switchSession = useChatStore((s) => s.switchSession);
  const loadHistoryForCurrent = useChatStore((s) => s.loadHistoryForCurrent);

  // 登录用户挂载时刷一下当前 session 的历史(localStorage 里残留的旧 sessionId 可能在服务端有消息)
  useEffect(() => {
    if (hydrated && user) void loadHistoryForCurrent();
  }, [hydrated, user, loadHistoryForCurrent]);

  const queryClient = useQueryClient();
  const { data: sessions, isLoading: sessionsLoading } = useQuery({
    queryKey: ['chat-sessions'],
    queryFn: () => chatApi.listSessions(),
    enabled: !!user,
    refetchInterval: 15_000,
  });

  const deleteMutation = useMutation({
    mutationFn: (sid: string) => chatApi.deleteSession(sid),
    onSuccess: (_res, sid) => {
      message.success('已删除会话');
      void queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
      // 删的是当前会话:开新会话
      if (sid === sessionId) resetSession();
    },
    onError: (e) => message.error(e instanceof Error ? e.message : '删除失败'),
  });

  const handleNewSession = () => {
    resetSession();
    void queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
  };

  const handleSwitch = async (sid: string) => {
    if (sid === sessionId) return;
    await switchSession(sid);
  };

  return (
    <Layout style={{ minHeight: 'calc(100vh - 56px)', background: '#f5f6f8' }}>
      {user && (
        <Sider
          width={260}
          style={{
            background: '#fff',
            borderRight: '1px solid #f0f0f0',
            padding: 0,
          }}
        >
          <div style={{ padding: 16, borderBottom: '1px solid #f5f5f5' }}>
            <Button
              type="primary"
              block
              icon={<PlusOutlined />}
              onClick={handleNewSession}
            >
              新会话
            </Button>
          </div>
          <div
            style={{
              padding: '12px 12px',
              fontSize: 12,
              color: '#8c8c8c',
              letterSpacing: 0.5,
            }}
          >
            我的对话
          </div>
          <div style={{ padding: '0 8px 16px', overflowY: 'auto', height: 'calc(100vh - 56px - 110px)' }}>
            {sessionsLoading ? (
              <Skeleton active paragraph={{ rows: 4 }} style={{ padding: '0 8px' }} />
            ) : sessions && sessions.length > 0 ? (
              <Space orientation="vertical" size={4} style={{ width: '100%' }}>
                {sessions.map((s: SessionBrief) => (
                  <SessionItem
                    key={s.id}
                    session={s}
                    active={s.id === sessionId}
                    onClick={() => void handleSwitch(s.id)}
                    onDelete={() => deleteMutation.mutate(s.id)}
                  />
                ))}
              </Space>
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={<Text type="secondary">还没对话</Text>}
                style={{ marginTop: 24 }}
              />
            )}
          </div>
        </Sider>
      )}

      <Content style={{ display: 'flex', justifyContent: 'center', padding: '24px 16px' }}>
        <div
          style={{
            width: '100%',
            maxWidth: 920,
            background: '#fff',
            borderRadius: 12,
            boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
            height: 'calc(100vh - 56px - 48px)',
          }}
        >
          <header
            style={{
              padding: '16px 24px',
              borderBottom: '1px solid #f0f0f0',
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              flexShrink: 0,
            }}
          >
            <RobotOutlined style={{ fontSize: 24, color: '#1677ff' }} />
            <div style={{ flex: 1 }}>
              <Title level={5} style={{ margin: 0 }}>
                AI 导购对话
              </Title>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {user ? (
                  <>会话 · {sessionId ? sessionId.slice(0, 8) : '...'} · 历史在左侧</>
                ) : (
                  <>未登录;聊天可用但不保存历史。<a href="/login">去登录</a></>
                )}
              </Text>
            </div>
            <Tooltip title="开新一段对话">
              <Button icon={<ClearOutlined />} onClick={handleNewSession}>
                新会话
              </Button>
            </Tooltip>
          </header>

          <div style={{ flex: 1, minHeight: 0, padding: '0 24px 16px' }}>
            <ChatBody />
          </div>
        </div>
      </Content>
    </Layout>
  );
}

function SessionItem({
  session,
  active,
  onClick,
  onDelete,
}: {
  session: SessionBrief;
  active: boolean;
  onClick: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      onClick={onClick}
      style={{
        padding: '8px 10px',
        borderRadius: 8,
        cursor: 'pointer',
        background: active ? '#e6f4ff' : 'transparent',
        display: 'flex',
        alignItems: 'flex-start',
        gap: 8,
        transition: 'background 120ms',
      }}
      onMouseEnter={(e) => {
        if (!active) (e.currentTarget as HTMLDivElement).style.background = '#fafafa';
      }}
      onMouseLeave={(e) => {
        if (!active) (e.currentTarget as HTMLDivElement).style.background = 'transparent';
      }}
    >
      <MessageOutlined style={{ marginTop: 4, color: active ? '#1677ff' : '#8c8c8c' }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 13,
            color: active ? '#1677ff' : '#262626',
            fontWeight: active ? 500 : 400,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {session.title || '未命名会话'}
        </div>
        <div style={{ fontSize: 11, color: '#bfbfbf', marginTop: 2 }}>
          {session.message_count} 条 · {new Date(session.updated_at).toLocaleDateString()}
        </div>
      </div>
      <Popconfirm
        title="删除这段会话?"
        okText="删除"
        cancelText="取消"
        okButtonProps={{ danger: true }}
        onConfirm={(e) => {
          e?.stopPropagation();
          onDelete();
        }}
      >
        <Button
          type="text"
          size="small"
          icon={<DeleteOutlined />}
          onClick={(e) => e.stopPropagation()}
        />
      </Popconfirm>
    </div>
  );
}
