'use client';

import { useState } from 'react';
import { LockOutlined, MobileOutlined, UserOutlined } from '@ant-design/icons';
import {
  App as AntApp,
  Button,
  Card,
  Form,
  Input,
  Space,
  Tabs,
  Typography,
} from 'antd';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { authApi } from '../../lib/api/auth';
import { ApiError } from '../../lib/api/client';
import { useAuthStore } from '../../store/authStore';

const { Title, Text } = Typography;

export default function LoginPage() {
  const router = useRouter();
  const { message } = AntApp.useApp();
  const applyToken = useAuthStore((s) => s.applyToken);
  const [loading, setLoading] = useState(false);

  const handlePasswordLogin = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const token = await authApi.login(values.username, values.password);
      await applyToken(token);
      message.success('登录成功');
      // 管理员登录直接进后台,其它角色回首页
      const role = useAuthStore.getState().user?.role;
      router.push(role === 'admin' ? '/admin' : role === 'merchant' ? '/merchant' : '/');
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : '登录失败';
      message.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleSmsLogin = async (values: { phone: string; code: string }) => {
    setLoading(true);
    try {
      const token = await authApi.smsLogin({ phone: values.phone, code: values.code });
      await applyToken(token);
      message.success('登录成功');
      router.push('/');
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : '登录失败';
      message.error(msg);
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
        background: '#f5f6f8',
      }}
    >
      <Card style={{ width: 420, borderRadius: 12 }} styles={{ body: { padding: 28 } }}>
        <Title level={3} style={{ marginBottom: 8 }}>
          登录 RAG-Agent
        </Title>
        <Text type="secondary">已有账号?选一种方式登录。</Text>

        <Tabs
          defaultActiveKey="password"
          style={{ marginTop: 16 }}
          items={[
            {
              key: 'password',
              label: '账密登录',
              children: (
                <Form layout="vertical" onFinish={handlePasswordLogin} size="large">
                  <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
                    <Input prefix={<UserOutlined />} placeholder="用户名" autoComplete="username" />
                  </Form.Item>
                  <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
                    <Input.Password
                      prefix={<LockOutlined />}
                      placeholder="密码"
                      autoComplete="current-password"
                    />
                  </Form.Item>
                  <Button type="primary" htmlType="submit" loading={loading} block size="large">
                    登录
                  </Button>
                  <Text
                    type="secondary"
                    style={{ display: 'block', textAlign: 'center', fontSize: 12, marginTop: 12 }}
                  >
                    管理员请用预置账号 admin / admin123 登录(不能通过页面注册)
                  </Text>
                </Form>
              ),
            },
            {
              key: 'sms',
              label: '手机号 + 验证码',
              children: <SmsForm onSubmit={handleSmsLogin} loading={loading} />,
            },
          ]}
        />

        <div style={{ marginTop: 16, textAlign: 'center' }}>
          <Space size={16}>
            <Link href="/register">
              <Text type="secondary">注册账号</Text>
            </Link>
            <Link href="/register/merchant">
              <Text type="secondary">商家入驻</Text>
            </Link>
          </Space>
        </div>
      </Card>
    </div>
  );
}

function SmsForm({
  onSubmit,
  loading,
}: {
  onSubmit: (v: { phone: string; code: string }) => Promise<void>;
  loading: boolean;
}) {
  const [form] = Form.useForm();
  const { message } = AntApp.useApp();
  const [sendCooldown, setSendCooldown] = useState(0);

  const handleSendCode = async () => {
    try {
      const phone = await form.validateFields(['phone']).then((v) => v.phone);
      await authApi.sendSms(phone);
      message.success('验证码已发送');
      let left = 60;
      setSendCooldown(left);
      const t = setInterval(() => {
        left -= 1;
        if (left <= 0) {
          clearInterval(t);
          setSendCooldown(0);
        } else {
          setSendCooldown(left);
        }
      }, 1000);
    } catch (err) {
      if (err instanceof ApiError) message.error(err.message);
    }
  };

  return (
    <Form form={form} layout="vertical" onFinish={onSubmit} size="large">
      <Form.Item
        name="phone"
        rules={[
          { required: true, message: '请输入手机号' },
          { pattern: /^1[3-9]\d{9}$/, message: '手机号格式不对' },
        ]}
      >
        <Input prefix={<MobileOutlined />} placeholder="手机号" autoComplete="tel" />
      </Form.Item>
      <Form.Item name="code" rules={[{ required: true, message: '请输入验证码' }]}>
        <Space.Compact style={{ width: '100%' }}>
          <Input placeholder="6 位验证码" maxLength={6} autoComplete="one-time-code" />
          <Button onClick={handleSendCode} disabled={sendCooldown > 0}>
            {sendCooldown > 0 ? `${sendCooldown}s` : '获取'}
          </Button>
        </Space.Compact>
      </Form.Item>
      <Button type="primary" htmlType="submit" loading={loading} block size="large">
        登录
      </Button>
    </Form>
  );
}
