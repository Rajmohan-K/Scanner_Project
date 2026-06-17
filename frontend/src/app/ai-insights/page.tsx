"use client";

import React, { useEffect, useMemo, useState } from 'react';
import { Brain, RefreshCw, ShieldAlert, Sparkles, Target, TrendingUp } from 'lucide-react';
import { getV20Dashboard, refreshV20Dashboard } from '@/lib/api';
import { useToast } from '@/components/layout/ToastProvider';
import { DataTable, EmptyState, MetricTile, PageHero, TerminalPanel } from '@/components/terminal/TerminalPrimitives';

export default function AiInsightsPage() {
  const toast = useToast();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const loadingRef = React.useRef(false);

  async function load(refresh = false, silent = false) {
    if (loadingRef.current) return;
    try {
      loadingRef.current = true;
      if (!silent) setLoading(true);
      const payload = refresh ? await refreshV20Dashboard() : await getV20Dashboard();
      setData(payload);
      if (refresh) toast?.push('Live AI insights refreshed', 'success');
    } catch {
      if (!silent) {
        setData(null);
        toast?.push('Unable to load AI insights', 'error');
      }
    } finally {
      setLoading(false);
      loadingRef.current = false;
    }
  }

  useEffect(() => {
    load();
    const timer = window.setInterval(() => load(false, true), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const insights = data?.ai_insights || [];
  const stocks = data?.top_stocks || [];
  const rows = useMemo(() => stocks.slice(0, 20).map((stock: any) => [
    <strong key={`${stock.symbol}-symbol`}>{stock.symbol}</strong>,
    stock.sector || '-',
    stock.ai_rating || '-',
    stock.profitability_score ?? stock.final_ai_score ?? '-',
    stock.growth_score ?? '-',
    stock.value_score ?? '-',
    stock.momentum_score ?? '-',
    stock.risk_score ?? '-',
    stock.reasoning || stock.reason || '-',
  ]), [stocks]);

  return (
    <main>
      <PageHero
        eyebrow="AI Insights"
        title="Live Intelligence Board"
        description="Backend-generated profitability, momentum, valuation, quality, and risk insights from the current V20 opportunity universe."
        actions={<button className="btn-primary" type="button" onClick={() => load(true)}><RefreshCw size={16} /> Refresh Insights</button>}
        metrics={[
          { label: 'Insight Cards', value: loading ? 'Loading' : String(insights.length), tone: insights.length ? 'good' : 'warn' },
          { label: 'Ranked Stocks', value: String(stocks.length), tone: stocks.length ? 'good' : 'warn' },
          { label: 'Data Source', value: 'Live V20 API', tone: 'good' },
        ]}
      />

      <div className="metric-grid">
        <MetricTile label="Top Pick" value={insights[0]?.symbol || '-'} detail={insights[0]?.rating || 'waiting for backend'} icon={Sparkles} tone={insights[0] ? 'good' : 'warn'} />
        <MetricTile label="Momentum" value={insights.find((item: any) => /momentum/i.test(item.title))?.symbol || '-'} detail="from scoring engine" icon={TrendingUp} tone="good" />
        <MetricTile label="Risk Watch" value={insights.find((item: any) => /risk/i.test(item.title))?.symbol || '-'} detail="highest backend risk score" icon={ShieldAlert} tone="warn" />
        <MetricTile label="AI Model" value="Active" detail="scoring explanations enabled" icon={Brain} tone="good" />
      </div>

      <TerminalPanel eyebrow="Live AI Cards" title="Recommendation Explanations">
        {insights.length ? (
          <div className="ai-insight-grid">
            {insights.map((insight: any) => (
              <article key={`${insight.title}-${insight.symbol}`} className="ai-insight-card">
                <Target size={18} />
                <span>{insight.title}</span>
                <strong>{insight.symbol}</strong>
                <p>{insight.reason}</p>
                <b>{insight.rating}</b>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="No AI insights available" body="Run or refresh the live V20 scanner to populate backend AI recommendations." />
        )}
      </TerminalPanel>

      <TerminalPanel eyebrow="Ranked Intelligence" title="Backend Scoring Matrix">
        <DataTable
          columns={['Stock', 'Sector', 'Rating', 'Profitability', 'Growth', 'Value', 'Momentum', 'Risk', 'Reason']}
          rows={rows}
        />
      </TerminalPanel>
    </main>
  );
}
