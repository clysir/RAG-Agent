/**
 * 思考链可视化:把 chatStore.thoughtSteps 渲染成 AntD X ThoughtChain。
 *
 * 显示规则:
 *   - 流式中 / 上轮刚结束都会显示
 *   - 用户开新轮,会被 chatStore.send 自动清空重建
 *   - 只露大标题(意图 / 召回 / 精排 / 生成),不暴露 topK / 阈值等实现细节
 */

'use client';

import { ThoughtChain } from '@ant-design/x';
import { Card } from 'antd';
import { useChatStore } from '../../store/chatStore';
import type { AgentState } from '../../lib/types';
import type { ThoughtStep } from '../../store/chatStore';

const STATE_LABEL: Record<AgentState, string> = {
  intent: '意图识别',
  load_memory: '加载长期记忆',
  image_understand: '图像理解',
  query_rewrite: '查询改写',
  retrieve: '多路召回',
  rerank: '精排',
  web_fallback: '联网搜索',
  need_clarify: '反问澄清',
  respond: '生成回答',
  end: '完成',
};

// AntD X ThoughtChain status:'success' | 'loading' | 'error' | 'abort' | undefined
function mapStatus(s: ThoughtStep['status']): 'success' | 'loading' {
  return s === 'done' ? 'success' : 'loading';
}

export function ThoughtChainPanel() {
  const steps = useChatStore((s) => s.thoughtSteps);
  if (steps.length === 0) return null;

  const items = steps
    .filter((s) => s.state !== 'end') // end 状态不显示,只用来标完成
    .map((step, idx) => ({
      key: `${step.state}-${idx}`,
      title: STATE_LABEL[step.state],
      status: mapStatus(step.status),
    }));

  if (items.length === 0) return null;

  return (
    <Card size="small" style={{ marginBottom: 12, borderRadius: 10 }} styles={{ body: { padding: '12px 16px' } }}>
      <div style={{ fontSize: 12, color: '#8c8c8c', marginBottom: 8 }}>思考链</div>
      <ThoughtChain items={items} />
    </Card>
  );
}
