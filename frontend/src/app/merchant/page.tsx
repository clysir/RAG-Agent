'use client';

import { useEffect, useState } from 'react';
import { ShopOutlined, UploadOutlined } from '@ant-design/icons';
import {
  App as AntApp,
  Button,
  Card,
  Empty,
  Form,
  Image,
  Input,
  InputNumber,
  Select,
  Skeleton,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
  type UploadProps,
} from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { merchantApi } from '../../lib/api/merchant';
import { uploadApi } from '../../lib/api/upload';
import { useAuthStore } from '../../store/authStore';
import type { SubmissionBrief, SubmissionStatus } from '../../lib/types';

type CustomUploadArg = Parameters<NonNullable<UploadProps['customRequest']>>[0];

const { Title, Text } = Typography;

const STATUS_TAG: Record<SubmissionStatus, { color: string; label: string }> = {
  pending: { color: 'gold', label: '待审核' },
  approved: { color: 'green', label: '已通过' },
  rejected: { color: 'red', label: '已驳回' },
};

const CATEGORIES = ['服饰', '鞋包', '美妆', '家居', '数码', '食品', '母婴', '运动', '其他'];

export default function MerchantPage() {
  const router = useRouter();
  const { message } = AntApp.useApp();
  const { user, hydrated } = useAuthStore();
  const queryClient = useQueryClient();
  const [form] = Form.useForm();
  const [imageInfo, setImageInfo] = useState<{ key: string; url: string } | null>(null);

  useEffect(() => {
    if (hydrated && (!user || user.role !== 'merchant')) {
      message.warning('只有商家账号才能进入商家中心');
      router.replace('/');
    }
  }, [hydrated, user, router]);

  const { data, isLoading } = useQuery({
    queryKey: ['merchant-submissions'],
    queryFn: () => merchantApi.mySubmissions(),
    enabled: !!user && user.role === 'merchant',
  });

  const submitMutation = useMutation({
    mutationFn: merchantApi.submit,
    onSuccess: () => {
      message.success('已提交,等待管理员审核。审核通过后约 10s 内可被检索。');
      form.resetFields();
      setImageInfo(null);
      void queryClient.invalidateQueries({ queryKey: ['merchant-submissions'] });
    },
    onError: (err) => message.error(err instanceof Error ? err.message : '提交失败'),
  });

  const onUpload = async (opt: CustomUploadArg) => {
    const file = opt.file as File;
    try {
      const res = await uploadApi.image(file);
      setImageInfo({ key: res.object_key, url: res.url });
      opt.onSuccess?.(res);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '上传失败');
      opt.onError?.(err as Error);
    }
  };

  const handleSubmit = (values: {
    title: string;
    category: string;
    price: number;
    brand?: string;
    description?: string;
    stock: number;
  }) => {
    submitMutation.mutate({
      ...values,
      image_object_key: imageInfo?.key,
    });
  };

  if (!hydrated || !user || user.role !== 'merchant') {
    return <Skeleton style={{ margin: 24 }} active />;
  }

  const submissionColumns = [
    { title: '#', dataIndex: 'id', width: 60 },
    { title: '标题', dataIndex: 'title' },
    { title: '类目', dataIndex: 'category', width: 100 },
    {
      title: '价格',
      dataIndex: 'price',
      width: 100,
      render: (p: number) => <Text type="danger">¥{p.toFixed(0)}</Text>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (s: SubmissionStatus) => <Tag color={STATUS_TAG[s].color}>{STATUS_TAG[s].label}</Tag>,
    },
    {
      title: '提交时间',
      dataIndex: 'created_at',
      width: 180,
      render: (s: string) => <Text type="secondary">{new Date(s).toLocaleString()}</Text>,
    },
  ];

  return (
    <div style={{ maxWidth: 1100, margin: '24px auto', padding: '0 16px' }}>
      <Card style={{ borderRadius: 12 }}>
        <Space size={10} style={{ marginBottom: 16 }}>
          <ShopOutlined style={{ fontSize: 20, color: '#1677ff' }} />
          <Title level={4} style={{ margin: 0 }}>
            商家中心
          </Title>
        </Space>
        <Tabs
          defaultActiveKey="new"
          items={[
            {
              key: 'new',
              label: '提交新商品',
              children: (
                <div style={{ maxWidth: 640 }}>
                  <Form form={form} layout="vertical" onFinish={handleSubmit} initialValues={{ stock: 100 }}>
                    <Form.Item label="标题" name="title" rules={[{ required: true }]}>
                      <Input maxLength={120} placeholder="商品标题" />
                    </Form.Item>
                    <Space wrap style={{ width: '100%' }}>
                      <Form.Item label="类目" name="category" rules={[{ required: true }]} style={{ width: 200 }}>
                        <Select options={CATEGORIES.map((c) => ({ value: c, label: c }))} />
                      </Form.Item>
                      <Form.Item label="品牌" name="brand" style={{ width: 200 }}>
                        <Input />
                      </Form.Item>
                      <Form.Item label="价格(¥)" name="price" rules={[{ required: true }]} style={{ width: 140 }}>
                        <InputNumber min={0} style={{ width: '100%' }} />
                      </Form.Item>
                      <Form.Item label="库存" name="stock" rules={[{ required: true }]} style={{ width: 140 }}>
                        <InputNumber min={0} style={{ width: '100%' }} />
                      </Form.Item>
                    </Space>
                    <Form.Item label="描述" name="description">
                      <Input.TextArea rows={3} maxLength={500} showCount />
                    </Form.Item>
                    <Form.Item label="商品主图">
                      <Space align="start">
                        <Upload
                          accept="image/*"
                          showUploadList={false}
                          customRequest={onUpload}
                        >
                          <Button icon={<UploadOutlined />}>选择图片</Button>
                        </Upload>
                        {imageInfo && (
                          <Image
                            src={imageInfo.url}
                            width={88}
                            height={88}
                            style={{ borderRadius: 6, objectFit: 'cover' }}
                          />
                        )}
                      </Space>
                    </Form.Item>
                    <Button type="primary" htmlType="submit" loading={submitMutation.isPending}>
                      提交审核
                    </Button>
                  </Form>
                </div>
              ),
            },
            {
              key: 'list',
              label: '我的提交',
              children:
                !isLoading && (!data || data.length === 0) ? (
                  <Empty description="还没提交过商品" />
                ) : (
                  <Table
                    rowKey="id"
                    loading={isLoading}
                    columns={submissionColumns}
                    dataSource={(data ?? []) as SubmissionBrief[]}
                    pagination={{ pageSize: 20 }}
                  />
                ),
            },
          ]}
        />
      </Card>
    </div>
  );
}
