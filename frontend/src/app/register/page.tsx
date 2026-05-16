'use client';

import { useState } from 'react';
import { LockOutlined, MailOutlined, UserOutlined } from '@ant-design/icons';
import { App as AntApp, Button, Card, Form, Input, Typography } from 'antd';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { authApi } from '../../lib/api/auth';
import { ApiError } from '../../lib/api/client';

const { Title, Text } = Typography;

export default function RegisterPage() {
  const router = useRouter();
  const { message } = AntApp.useApp();
  const [loading, setLoading] = useState(false);

  const onFinish = async (values: { username: string; email?: string; password: string }) => {
    setLoading(true);
    try {
      await authApi.register(values);
      message.success('注册成功,去登录');
      router.push('/login');
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : '注册失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: 'calc(100vh - 56px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
      }}
    >
      <Card style={{ width: 420, borderRadius: 12 }} styles={{ body: { padding: 28 } }}>
        <Title level={3} style={{ marginBottom: 8 }}>
          注册账号
        </Title>
        <Text type="secondary">注册后可以聊天 + 长期记忆 + 商品浏览</Text>

        <Form layout="vertical" onFinish={onFinish} size="large" style={{ marginTop: 16 }}>
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名(3-20 位)" />
          </Form.Item>
          <Form.Item
            name="email"
            rules={[{ type: 'email', message: '邮箱格式不对' }]}
          >
            <Input prefix={<MailOutlined />} placeholder="邮箱(可选)" />
          </Form.Item>
          <Form.Item
            name="password"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 8, message: '密码至少 8 位' },
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="密码(至少 8 位)" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} block size="large">
            注册
          </Button>
        </Form>

        <div style={{ marginTop: 16, textAlign: 'center' }}>
          <Link href="/login">
            <Text type="secondary">已有账号,直接登录</Text>
          </Link>
        </div>
      </Card>
    </div>
  );
}
