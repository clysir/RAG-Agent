'use client';

import { useState } from 'react';
import { IdcardOutlined, LockOutlined, MailOutlined, ShopOutlined, UserOutlined } from '@ant-design/icons';
import { App as AntApp, Button, Card, Form, Input, Typography } from 'antd';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { authApi } from '../../../lib/api/auth';
import { ApiError } from '../../../lib/api/client';

const { Title, Text } = Typography;

export default function MerchantRegisterPage() {
  const router = useRouter();
  const { message } = AntApp.useApp();
  const [loading, setLoading] = useState(false);

  const onFinish = async (values: {
    username: string;
    email?: string;
    password: string;
    shop_name: string;
    business_license: string;
  }) => {
    setLoading(true);
    try {
      await authApi.registerMerchant(values);
      message.success('入驻申请已提交,待管理员审核');
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
      <Card style={{ width: 460, borderRadius: 12 }} styles={{ body: { padding: 28 } }}>
        <Title level={3} style={{ marginBottom: 8 }}>
          商家入驻
        </Title>
        <Text type="secondary">提交后,管理员审核通过即可在系统上架商品。</Text>

        <Form layout="vertical" onFinish={onFinish} size="large" style={{ marginTop: 16 }}>
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" />
          </Form.Item>
          <Form.Item name="email" rules={[{ type: 'email' }]}>
            <Input prefix={<MailOutlined />} placeholder="邮箱(可选)" />
          </Form.Item>
          <Form.Item
            name="password"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 8 },
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="密码(至少 8 位)" />
          </Form.Item>
          <Form.Item name="shop_name" rules={[{ required: true, message: '请输入店铺名' }]}>
            <Input prefix={<ShopOutlined />} placeholder="店铺名称" />
          </Form.Item>
          <Form.Item name="business_license" rules={[{ required: true, message: '请输入营业执照号' }]}>
            <Input prefix={<IdcardOutlined />} placeholder="营业执照号" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} block size="large">
            提交入驻申请
          </Button>
        </Form>

        <div style={{ marginTop: 16, textAlign: 'center' }}>
          <Link href="/register">
            <Text type="secondary">注册普通用户</Text>
          </Link>
        </div>
      </Card>
    </div>
  );
}
