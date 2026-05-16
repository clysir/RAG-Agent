/**
 * 悬浮聊天:
 *   - 关闭态:右下角 FAB(用 AntD FloatButton)
 *   - 展开态:浮在右下角的 420×640 卡片,头部带"展开为完整页"按钮
 *
 * 路由 /chat 上自动隐藏(完整页已经有了),其他页都常驻。
 */

'use client';

import { CloseOutlined, ExpandAltOutlined, MessageOutlined, ReloadOutlined } from '@ant-design/icons';
import { FloatButton, theme, Tooltip } from 'antd';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useChatStore } from '../../store/chatStore';
import { ChatBody } from './ChatBody';

const PANEL_WIDTH = 420;
const PANEL_HEIGHT = 640;

export function FloatingChat() {
  const pathname = usePathname();
  const open = useChatStore((s) => s.floatingOpen);
  const toggle = useChatStore((s) => s.toggleFloating);
  const resetSession = useChatStore((s) => s.resetSession);
  const { token } = theme.useToken();

  // 完整聊天页用不到悬浮气泡
  if (pathname?.startsWith('/chat')) return null;

  if (!open) {
    return (
      <FloatButton
        icon={<MessageOutlined />}
        type="primary"
        tooltip="问问 AI 导购"
        onClick={() => toggle(true)}
        style={{ right: 28, bottom: 28, width: 52, height: 52 }}
      />
    );
  }

  return (
    <div
      style={{
        position: 'fixed',
        right: 28,
        bottom: 28,
        width: PANEL_WIDTH,
        height: PANEL_HEIGHT,
        maxHeight: 'calc(100vh - 120px)',
        background: '#fff',
        borderRadius: 16,
        boxShadow: '0 12px 32px rgba(0, 0, 0, 0.18)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        zIndex: 1100,
        border: `1px solid ${token.colorBorderSecondary}`,
      }}
    >
      <header
        style={{
          height: 48,
          padding: '0 12px 0 16px',
          background: token.colorPrimary,
          color: '#fff',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          flexShrink: 0,
        }}
      >
        <MessageOutlined />
        <span style={{ fontWeight: 600, flex: 1 }}>AI 导购</span>
        <Tooltip title="新会话">
          <button
            onClick={() => resetSession()}
            style={iconBtnStyle}
            aria-label="新会话"
          >
            <ReloadOutlined />
          </button>
        </Tooltip>
        <Tooltip title="展开为完整页">
          <Link href="/chat" onClick={() => toggle(false)}>
            <button style={iconBtnStyle} aria-label="展开为完整页">
              <ExpandAltOutlined />
            </button>
          </Link>
        </Tooltip>
        <Tooltip title="关闭">
          <button onClick={() => toggle(false)} style={iconBtnStyle} aria-label="关闭">
            <CloseOutlined />
          </button>
        </Tooltip>
      </header>

      <div style={{ flex: 1, minHeight: 0 }}>
        <ChatBody compact />
      </div>
    </div>
  );
}

const iconBtnStyle: React.CSSProperties = {
  width: 28,
  height: 28,
  border: 'none',
  background: 'transparent',
  color: '#fff',
  cursor: 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  borderRadius: 6,
};
