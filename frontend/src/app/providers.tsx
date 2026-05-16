/**
 * 全局 Providers 包装(必须是 client component,因为 QueryClient / AntdRegistry 都依赖客户端)。
 *
 * 顺序:
 *   AntdRegistry      → 让 antd 在 Next.js App Router 下 SSR 不闪烁
 *     ConfigProvider  → 主题色 / 中文 locale / 紧凑度
 *       App           → 让 message / notification / Modal 静态调用能 consume 动态主题
 *         XProvider   → AntD X 的全局 token(气泡颜色等)
 *           QueryClientProvider → TanStack Query
 *             AuthHydrator      → 首次挂载 hydrate authStore
 *               children
 */

'use client';

import { AntdRegistry } from '@ant-design/nextjs-registry';
import { App, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { XProvider } from '@ant-design/x';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { AuthHydrator } from '../components/auth/AuthHydrator';
import { ChatHydrator } from '../components/chat/ChatHydrator';

const themeToken = {
  colorPrimary: '#1677ff',
  colorBgLayout: '#f5f6f8',
  borderRadius: 10,
};

export function Providers({ children }: { children: ReactNode }) {
  // QueryClient 在组件内 useState,SSR / CSR 才不会共享同一份缓存
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30 * 1000,
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      }),
  );

  return (
    <AntdRegistry>
      <ConfigProvider locale={zhCN} theme={{ token: themeToken }}>
        <App component={false}>
          <XProvider locale={zhCN} theme={{ token: themeToken }}>
            <QueryClientProvider client={queryClient}>
              <AuthHydrator />
              <ChatHydrator />
              {children}
            </QueryClientProvider>
          </XProvider>
        </App>
      </ConfigProvider>
    </AntdRegistry>
  );
}
