/**
 * 顶部导航条:logo + 路由链接 + 右侧用户菜单。
 *
 * 商家 / 管理员入口仅对应角色显示。
 */

'use client';

import { Avatar, Button, Dropdown, Space, theme } from 'antd';
import { LogoutOutlined, MessageOutlined, ProfileOutlined, RobotOutlined, ShopOutlined, UserOutlined } from '@ant-design/icons';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '../../store/authStore';

export function TopNav() {
  const { user, logout } = useAuthStore();
  const router = useRouter();
  const { token } = theme.useToken();

  const onLogout = () => {
    logout();
    router.push('/');
  };

  // 用户菜单(已登录态)
  const userMenuItems = [
    {
      key: 'memory',
      icon: <ProfileOutlined />,
      label: <Link href="/settings/memory">我的记忆</Link>,
    },
    ...(user?.role === 'merchant'
      ? [
          {
            key: 'merchant',
            icon: <ShopOutlined />,
            label: <Link href="/merchant">商家中心</Link>,
          },
        ]
      : []),
    ...(user?.role === 'admin'
      ? [
          {
            key: 'admin',
            icon: <ShopOutlined />,
            label: <Link href="/admin">管理后台</Link>,
          },
        ]
      : []),
    { type: 'divider' as const },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      danger: true,
      label: '退出登录',
      onClick: onLogout,
    },
  ];

  return (
    <header
      style={{
        height: 56,
        padding: '0 24px',
        background: '#fff',
        borderBottom: `1px solid ${token.colorBorderSecondary}`,
        display: 'flex',
        alignItems: 'center',
        gap: 24,
        position: 'sticky',
        top: 0,
        zIndex: 50,
      }}
    >
      <Link href="/" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <RobotOutlined style={{ fontSize: 22, color: token.colorPrimary }} />
        <span style={{ fontWeight: 600, fontSize: 16, color: token.colorText }}>RAG-Agent</span>
        <span style={{ color: token.colorTextTertiary, fontSize: 12 }}>多模态电商导购</span>
      </Link>

      <Space size="middle" style={{ marginLeft: 8 }}>
        <Link href="/">
          <Button type="text">商品</Button>
        </Link>
        <Link href="/chat">
          <Button type="text" icon={<MessageOutlined />}>
            聊天
          </Button>
        </Link>
      </Space>

      <div style={{ flex: 1 }} />

      {user ? (
        <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
          <Space style={{ cursor: 'pointer' }}>
            <Avatar size={32} icon={<UserOutlined />} style={{ background: token.colorPrimary }} />
            <span style={{ color: token.colorText }}>
              {user.username || user.phone || `用户 ${user.id}`}
            </span>
          </Space>
        </Dropdown>
      ) : (
        <Space>
          <Link href="/login">
            <Button type="text">登录</Button>
          </Link>
          <Link href="/register">
            <Button type="primary">注册</Button>
          </Link>
        </Space>
      )}
    </header>
  );
}
