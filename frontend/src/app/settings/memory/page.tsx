'use client';

import { DeleteOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Empty,
  Modal,
  Popconfirm,
  Skeleton,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { memoryApi } from '../../../lib/api/memory';
import { useAuthStore } from '../../../store/authStore';
import type { FactType, MemoryItem } from '../../../lib/types';

const { Title, Text } = Typography;

const FACT_TYPE_LABEL: Record<FactType, string> = {
  PREFERENCE: '偏好',
  SIZE: '尺寸',
  BRAND: '品牌',
  BUDGET: '预算',
  ALLERGY: '过敏',
  OCCUPATION: '职业',
  OTHER: '其他',
};

const FACT_TYPE_COLOR: Record<FactType, string> = {
  PREFERENCE: 'blue',
  SIZE: 'cyan',
  BRAND: 'geekblue',
  BUDGET: 'gold',
  ALLERGY: 'red',
  OCCUPATION: 'purple',
  OTHER: 'default',
};

export default function MemoryPage() {
  const router = useRouter();
  const { message } = AntApp.useApp();
  const { user, hydrated } = useAuthStore();
  const queryClient = useQueryClient();

  // 未登录跳走
  useEffect(() => {
    if (hydrated && !user) router.replace('/login');
  }, [hydrated, user, router]);

  const { data, isLoading } = useQuery({
    queryKey: ['memory'],
    queryFn: () => memoryApi.list({ limit: 100 }),
    enabled: !!user,
  });

  const removeMutation = useMutation({
    mutationFn: (id: number) => memoryApi.remove(id),
    onSuccess: () => {
      message.success('已删除');
      void queryClient.invalidateQueries({ queryKey: ['memory'] });
    },
    onError: (err) => message.error(err instanceof Error ? err.message : '删除失败'),
  });

  const forgetAll = async () => {
    const res = await memoryApi.forgetAll();
    message.success(`已忘记 ${res.invalidated} 条`);
    void queryClient.invalidateQueries({ queryKey: ['memory'] });
  };

  if (!hydrated || !user) return <Skeleton style={{ margin: 24 }} active />;

  const columns = [
    {
      title: '类型',
      dataIndex: 'fact_type',
      width: 100,
      render: (t: FactType) => <Tag color={FACT_TYPE_COLOR[t]}>{FACT_TYPE_LABEL[t]}</Tag>,
    },
    {
      title: '内容',
      dataIndex: 'fact_text',
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      width: 90,
      render: (v: number) => <Text type="secondary">{(v * 100).toFixed(0)}%</Text>,
    },
    {
      title: '记忆时间',
      dataIndex: 'valid_from',
      width: 160,
      render: (s: string) => <Text type="secondary">{new Date(s).toLocaleString()}</Text>,
    },
    {
      title: '操作',
      width: 90,
      render: (_: unknown, row: MemoryItem) => (
        <Popconfirm
          title="确认忘记这条事实?"
          okText="忘记"
          cancelText="取消"
          onConfirm={() => removeMutation.mutate(row.id)}
        >
          <Button danger size="small" icon={<DeleteOutlined />}>
            忘记
          </Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <div style={{ maxWidth: 960, margin: '24px auto', padding: '0 16px' }}>
      <Card style={{ borderRadius: 12 }}>
        <Space style={{ justifyContent: 'space-between', width: '100%', marginBottom: 16 }}>
          <div>
            <Title level={4} style={{ margin: 0 }}>
              我的记忆
            </Title>
            <Text type="secondary">
              Agent 在对话中沉淀下来的关于你的事实。你随时可以查看 / 删除 / 一键忘记(PIPL 合规)。
            </Text>
          </div>
          <Button
            danger
            icon={<ExclamationCircleOutlined />}
            onClick={() =>
              Modal.confirm({
                title: '一键忘记所有记忆?',
                content: '操作后,所有已记录的事实都会被置为失效。Agent 之后的回答不会再引用它们。',
                okText: '确认忘记',
                cancelText: '取消',
                okButtonProps: { danger: true },
                onOk: forgetAll,
              })
            }
          >
            一键忘记
          </Button>
        </Space>

        {!isLoading && (!data || data.items.length === 0) ? (
          <Empty description="还没有任何记忆。聊几轮天,Agent 会自动记下你的偏好。" />
        ) : (
          <Table
            rowKey="id"
            loading={isLoading}
            columns={columns}
            dataSource={data?.items ?? []}
            pagination={{ pageSize: 20, showSizeChanger: false }}
            locale={{ emptyText: '暂无记忆' }}
          />
        )}

        <Alert
          type="info"
          showIcon
          style={{ marginTop: 16 }}
          title="这是给你看的;Agent 检索时会按 valid_to IS NULL 过滤,只看当前有效事实"
        />
      </Card>
    </div>
  );
}
