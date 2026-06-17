import './globals.css';
import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { PageShell } from '@/components/layout/PageShell';
import { GlobalHeader } from '@/components/organisms/GlobalHeader';
import TopMarketBar from '@/components/organisms/TopMarketBar';
import GrowwAutoScanner from '@/components/organisms/GrowwAutoScanner';
import ReduxProvider from '@/components/layout/ReduxProvider';
import ToastProvider from '@/components/layout/ToastProvider';

export const metadata: Metadata = {
  title: 'Scanner V10',
  description: 'Premium fintech stock intelligence platform for NSE screening, ranking, analysis, and reporting.',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <PageShell>
          <ReduxProvider>
            <ToastProvider>
              <GrowwAutoScanner />
              <div className="app-frame">
                <GlobalHeader />
                <div className="workspace-frame">
                  <TopMarketBar />
                  <div className="page-shell__content">{children}</div>
                </div>
              </div>
            </ToastProvider>
          </ReduxProvider>
        </PageShell>
      </body>
    </html>
  );
}
