'use client';

import { useEffect, useState } from 'react';
import { CheckOutlined, CloseOutlined, SafetyOutlined } from '@ant-design/icons';
import {
  App as AntApp,
  Button,
  Card,
  Image,
  Input,
  Modal,
  Segmented,
  Skeleton,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { adminApi } from '../../lib/api/admin';
import { useAuthStore } from '../../store/authStore';
import type { SubmissionBrief, SubmissionStatus } from '../../lib/types';

const { Title, Text } = Typography;

const STATUS_TAG: Record<SubmissionStatus, { color: string; label: string }> = {
  pending: { color: 'gold', label: '待审核' },
  approved: { color: 'green', label: '已通过' },
  rejected: { color: 'red', label: '已驳回' },
};

export default function AdminPage() {
  const router = useRouter();
  const { message } = AntApp.useApp();
  const { user, hydrated } = useAuthStore();
  const [tab, setTab] = useState<SubmissionStatus>('pending');
  const queryClient = useQueryClient();

  useEffect(() => {
    if (hydrated && (!user || user.role !== 'admin')) {
      message.warning('需要管理员权限');
      router.replace('/');
    }
  }, [hydrated, user, router]);

  const { data, isLoading } = useQuery({
    queryKey: ['admin-submissions', tab],
    queryFn: () => adminApi.submissions(tab),
    enabled: !!user && user.role === 'admin',
  });

  const approveMutation = useMutation({
    mutationFn: adminApi.approve,
    onSuccess: () => {
      message.success('已通过,后台已派发建索引任务');
      void queryClient.invalidateQueries({ queryKey: ['admin-submissions'] });
    },
    onError: (e) => message.error(e instanceof Error ? e.message : '操作失败'),
  });

  const rejectMutation = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) => adminApi.reject(id, reason),
    onSuccess: () => {
      message.success('已驳回');
      void queryClient.invalidateQueries({ queryKey: ['admin-submissions'] });
    },
    onError: (e) => message.error(e instanceof Error ? e.message : '操作失败'),
  });

  const handleReject = (row: SubmissionBrief) => {
    let reason = '';
    Modal.confirm({
      title: `驳回 #${row.id} ${row.title}`,
      content: (
        <Input.TextArea
          rows={3}
          onChange={(e) => (reason = e.target.value)}
          placeholder="驳回理由(必填)"
        />
      ),
      okText: '驳回',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => {
        if (!reason.trim()) {
          message.error('请填写驳回理由');
          return Promise.reject();
        }
        return rejectMutation.mutateAsync({ id: row.id, reason });
      },
    });
  };

  if (!hydrated || !user || user.role !== 'admin') {
    return <Skeleton style={{ margin: 24 }} active />;
  }

  const columns = [
    { title: '#', dataIndex: 'id', width: 60 },
    {
      title: '图',
      dataIndex: 'image_url',
      width: 70,
      render: (u?: string | null) =>
        u ? (
          <Image src={u} width={48} height={48} style={{ borderRadius: 6, objectFit: 'cover' }} />
        ) : (
          <Text type="secondary">无</Text>
        ),
    },
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
      title: '操作',
      width: 200,
      render: (_: unknown, row: SubmissionBrief) =>
        row.status === 'pending' ? (
          <Space>
            <Button
              type="primary"
              size="small"
              icon={<CheckOutlined />}
              loading={approveMutation.isPending}
              onClick={() => approveMutation.mutate(row.id)}
            >
              通过
            </Button>
            <Button
              danger
              size="small"
              icon={<CloseOutlined />}
              onClick={() => handleReject(row)}
            >
              驳回
            </Button>
          </Space>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
  ];

  return (
    <div style={{ maxWidth: 1280, margin: '24px auto', padding: '0 16px' }}>
      <Card style={{ borderRadius: 12 }}>
        <Space size={10} style={{ marginBottom: 16 }}>
          <SafetyOutlined style={{ fontSize: 20, color: '#1677ff' }} />
          <Title level={4} style={{ margin: 0 }}>
            管理员审核
          </Title>
        </Space>
        <Segmented
          value={tab}
          onChange={(v) => setTab(v as SubmissionStatus)}
          options={[
            { value: 'pending', label: '待审核' },
            { value: 'approved', label: '已通过' },
            { value: 'rejected', label: '已驳回' },
          ]}
          style={{ marginBottom: 16 }}
        />
        <Table
          rowKey="id"
          loading={isLoading}
          columns={columns}
          dataSource={(data ?? []) as SubmissionBrief[]}
          pagination={{ pageSize: 20 }}
        />
      </Card>
    </div>
  );
}
