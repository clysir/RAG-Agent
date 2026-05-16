import type { Metadata } from 'next';
import './globals.css';
import { Providers } from './providers';
import { TopNav } from '../components/nav/TopNav';
import { FloatingChat } from '../components/chat/FloatingChat';

export const metadata: Metadata = {
  title: 'RAG-Agent · 多模态电商导购',
  description: '你的贴心智能导购 Agent',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <Providers>
          <TopNav />
          <main style={{ minHeight: 'calc(100vh - 56px)' }}>{children}</main>
          {/* 全局悬浮聊天气泡;FloatingChat 内部会根据当前 pathname 决定是否隐藏 */}
          <FloatingChat />
        </Providers>
      </body>
    </html>
  );
}
