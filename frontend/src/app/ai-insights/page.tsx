"use client";

import React, { useEffect, useMemo, useState } from 'react';
import { BrainCircuit, Download, GitCompareArrows, RefreshCw, ShieldCheck, Sparkles, Target, TrendingUp } from 'lucide-react';
import {
  getAiMarketSummary,
  getAiScannerInsights,
  getFinalDecisions,
  getMetaScannerLatest,
  getMlPredictions,
  getV20Dashboard,
  runMetaScanner,
} from '@/lib/api';
import { useToast } from '@/components/layout/ToastProvider';
import { DataTable, EmptyState, MetricTile, PageHero, ProgressLine, TerminalPanel, Toolbar } from '@/components/terminal/TerminalPrimitives';

type IntelligenceTab = 'Final Decision' | 'Meta Scanner' | 'ML Predictions' | 'AI Insights';

function exportCsv(rows: any[], filename: string) {
  const headers = ['Symbol', 'Decision', 'Meta Score', 'AI Confidence', 'ML Confidence', 'Risk Score', 'Reason'];
  const lines = [headers.join(',')].concat(rows.map((row) => [
    row.symbol || row.stock || '',
    row.final_decision || row.recommendation || row.ai_rating || '',
    row.meta_score ?? row.profitability_score ?? '',
    row.ai_confidence ?? row.confidence_pct ?? '',
    row.ml_confidence ?? row.ml_probability ?? '',
    row.risk_score ?? '',
    `"${String(row.reason_selected || row.reason || row.reasoning || row.summary || '').replace(/"/g, '""')}"`,
  ].join(',')));
  const url = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export default function IntelligenceCenterPage() {
  const toast = useToast();
  const [activeTab, setActiveTab] = useState<IntelligenceTab>('Final Decision');
  const [timeframe, setTimeframe] = useState('intraday');
  const [query, setQuery] = useState('');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [showRejected, setShowRejected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [finalData, setFinalData] = useState<any>(null);
  const [metaData, setMetaData] = useState<any>(null);
  const [mlData, setMlData] = useState<any>(null);
  const [aiData, setAiData] = useState<any>(null);
  const [dashboardData, setDashboardData] = useState<any>(null);

  async function load(silent = false) {
    if (!silent) setLoading(true);
    setError('');
    try {
      const [finalPayload, metaPayload, mlPayload, scannerPayload, marketPayload, dashboardPayload] = await Promise.all([
        getFinalDecisions(timeframe),
        getMetaScannerLatest(timeframe),
        getMlPredictions(timeframe),
        getAiScannerInsights('dashboard'),
        getAiMarketSummary(),
        getV20Dashboard(),
      ]);
      setFinalData(finalPayload);
      setMetaData(metaPayload);
      setMlData(mlPayload);
      setAiData({ scanner: scannerPayload, market: marketPayload });
      setDashboardData(dashboardPayload);
    } catch (err: any) {
      setError(err?.message || 'Unable to load intelligence center');
      if (!silent) toast?.push('Unable to load backend intelligence APIs', 'error');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [timeframe]);
  useEffect(() => {
    if (!autoRefresh) return undefined;
    const timer = window.setInterval(() => load(true), 3000);
    return () => window.clearInterval(timer);
  }, [autoRefresh, timeframe]);

  async function recalculate() {
    setLoading(true);
    try {
      await runMetaScanner(timeframe);
      await load(true);
      toast?.push('Intelligence engines recalculated', 'success');
    } catch (err: any) {
      setError(err?.message || 'Recalculation failed');
      toast?.push('Intelligence recalculation failed', 'error');
    } finally {
      setLoading(false);
    }
  }

  const finalRows = useMemo(() => {
    const sourceRows = showRejected ? [...(finalData?.decisions || []), ...(finalData?.rejected || [])] : (finalData?.decisions || []);
    return sourceRows.filter((row: any) => String(row.symbol || '').toLowerCase().includes(query.toLowerCase()));
  }, [finalData, showRejected, query]);

  const metaRows = useMemo(() => (metaData?.results || []).filter((row: any) => String(row.symbol || '').toLowerCase().includes(query.toLowerCase())), [metaData, query]);
  const mlRows = useMemo(() => (mlData?.predictions || []).filter((row: any) => String(row.symbol || '').toLowerCase().includes(query.toLowerCase())), [mlData, query]);
  const aiInsights = aiData?.scanner?.insights?.length ? aiData.scanner.insights : dashboardData?.ai_insights || [];
  const aiRows = useMemo(() => (dashboardData?.top_stocks || []).filter((row: any) => String(row.symbol || '').toLowerCase().includes(query.toLowerCase())).slice(0, 30), [dashboardData, query]);
  const summary = finalData?.summary || {};
  const currentRows = activeTab === 'Final Decision' ? finalRows : activeTab === 'Meta Scanner' ? metaRows : activeTab === 'ML Predictions' ? mlRows : aiRows;

  return (
    <main className="terminal-page">
      <PageHero
        eyebrow="Intelligence Center"
        title="AI + ML + Meta + Final Decision"
        description="One backend-wired workspace for scanner agreement, model confirmation, AI explanations, and strict final trade decisions."
        actions={<><button className="btn-primary" onClick={recalculate} disabled={loading}><ShieldCheck size={16} /> Recalculate</button><button className="btn-secondary" onClick={() => load()}><RefreshCw size={16} /> Retry</button></>}
        metrics={[
          { label: 'Trade', value: String(summary.trade || 0), tone: summary.trade ? 'good' : 'info' },
          { label: 'Watch', value: String(summary.watch || 0), tone: summary.watch ? 'warn' : 'info' },
          { label: 'Rejected', value: String(summary.rejected || 0), tone: 'warn' },
        ]}
      />

      <div className="metric-grid">
        <MetricTile label="Final Decision" value={summary.trade ? `${summary.trade} trade` : 'No forced trade'} detail={finalData?.generated_at || 'waiting for backend'} icon={ShieldCheck} tone={summary.trade ? 'good' : 'warn'} />
        <MetricTile label="Meta Scanner" value={String(metaData?.summary?.shown || 0)} detail="strict opportunities shown" icon={GitCompareArrows} tone={metaData?.summary?.shown ? 'good' : 'warn'} />
        <MetricTile label="ML Predictions" value={String(mlData?.predictions?.length || 0)} detail="model rows from backend" icon={BrainCircuit} tone={mlData?.predictions?.length ? 'good' : 'warn'} />
        <MetricTile label="AI Insights" value={String(aiInsights.length || 0)} detail={aiData?.market?.recommendation || 'market AI pending'} icon={Sparkles} tone={aiInsights.length ? 'good' : 'warn'} />
      </div>

      <Toolbar
        search={query}
        setSearch={setQuery}
        tabs={['Final Decision', 'Meta Scanner', 'ML Predictions', 'AI Insights']}
        activeTab={activeTab}
        onTabChange={(tab) => setActiveTab(tab as IntelligenceTab)}
        right={<><select value={timeframe} onChange={(event) => setTimeframe(event.target.value)}><option value="intraday">Intraday</option><option value="swing">Swing</option><option value="long-term">Long Term</option></select><label className="toggle-pill"><input type="checkbox" checked={autoRefresh} onChange={(event) => setAutoRefresh(event.target.checked)} /> Auto-refresh</label><label className="toggle-pill"><input type="checkbox" checked={showRejected} onChange={(event) => setShowRejected(event.target.checked)} /> Audit rejected</label><button className="btn-secondary" onClick={() => exportCsv(currentRows, `${activeTab.toLowerCase().replace(/\\s+/g, '-')}.csv`)}><Download size={15} /> Export</button></>}
      />

      {error && <div className="status-badge status-bad">{error}</div>}

      {activeTab === 'Final Decision' && (
        <TerminalPanel eyebrow="Decision Engine" title="Strict Final Decisions" description={`Last updated: ${finalData?.generated_at || 'Not available'}`}>
          {loading && !finalData ? <EmptyState title="Loading decisions" body="Waiting for backend final decision engine." /> : (
            <DataTable
              columns={['Symbol', 'Decision', 'Grade', 'Meta', 'Risk', 'RR', 'Trade Plan', 'Reason']}
              rows={finalRows.map((row: any) => {
                const plan = row.trade_plan || {};
                return [
                  <strong key="s">{row.symbol}</strong>,
                  <span className={`status-badge ${row.should_trade ? 'status-good' : row.should_watch ? 'status-warn' : 'status-bad'}`} key="d">{row.final_decision}</span>,
                  row.trade_grade,
                  row.meta_score,
                  row.risk_score,
                  row.risk_reward_ratio || plan.risk_reward_ratio || '-',
                  `Entry ${plan.entry || '-'} / SL ${plan.stop_loss || '-'} / T1 ${plan.target_1 || '-'}`,
                  row.reason_selected || row.reason_rejected || row.decision_summary,
                ];
              })}
              emptyTitle="No trade-worthy opportunity"
              emptyBody={finalData?.message || 'The final decision engine did not find A or A+ opportunities.'}
            />
          )}
        </TerminalPanel>
      )}

      {activeTab === 'Meta Scanner' && (
        <TerminalPanel eyebrow="Meta Scanner" title="Cross-Scanner Confirmation" description={`Last updated: ${metaData?.generated_at || 'Not available'}`}>
          {loading && !metaData ? <EmptyState title="Loading Meta Scanner" body="Reading backend scan outputs and calculating strict meta scores." /> : (
            <DataTable
              columns={['Symbol', 'Scan Types Matched', 'Meta Score', 'AI Confidence', 'ML Confidence', 'Risk Score', 'Final Decision', 'Reason']}
              rows={metaRows.map((row: any) => [
                <strong key="s">{row.symbol}</strong>,
                (row.scan_types_matched || []).join(', '),
                row.meta_score,
                row.ai_confidence,
                row.ml_confidence,
                row.risk_score,
                <span className={`status-badge ${row.should_trade ? 'status-good' : 'status-warn'}`} key="d">{row.final_decision}</span>,
                row.reason_selected || row.reason,
              ])}
              emptyTitle="No high-confidence opportunity found"
              emptyBody={metaData?.message || 'Run scan-specific scanners first, then run Meta Scanner.'}
            />
          )}
        </TerminalPanel>
      )}

      {activeTab === 'ML Predictions' && (
        <TerminalPanel eyebrow="Backend ML data" title="Prediction Confidence Table" description={`Data freshness: ${mlData?.generated_at || 'Not available'}`}>
          {loading && !mlData ? <EmptyState title="Loading ML predictions" body="Waiting for backend model confidence rows." /> : (
            <DataTable
              columns={['Symbol', 'ML Confidence', 'AI Confidence', 'Backtest', 'Risk', 'Meta', 'Decision', 'Reason']}
              rows={mlRows.map((row: any) => [
                <strong key="s">{row.symbol}</strong>,
                <ProgressLine key="ml" value={Math.round(Number(row.ml_confidence || 0))} />,
                <ProgressLine key="ai" value={Math.round(Number(row.ai_confidence || 0))} />,
                row.backtest_score,
                row.risk_score,
                row.meta_score,
                row.final_decision,
                row.reason,
              ])}
              emptyTitle="No ML predictions available"
              emptyBody="Run scanner pages first, then refresh this ML prediction layer."
            />
          )}
        </TerminalPanel>
      )}

      {activeTab === 'AI Insights' && (
        <>
          <TerminalPanel eyebrow="Live AI Cards" title="Recommendation Explanations" description={aiData?.market?.summary || 'Market AI summary pending'}>
            {aiInsights.length ? (
              <div className="ai-insight-grid">
                {aiInsights.map((insight: any) => (
                  <article key={`${insight.title || insight.recommendation}-${insight.symbol || insight.stockSymbol}`} className="ai-insight-card">
                    <Target size={18} />
                    <span>{insight.scanType || insight.title || 'Stock Insight'}</span>
                    <strong>{insight.stockSymbol || insight.symbol}</strong>
                    <p>{insight.summary || insight.reason}</p>
                    <b>{insight.recommendation || insight.rating}</b>
                  </article>
                ))}
              </div>
            ) : (
              <EmptyState title="No AI insights available" body="Run or refresh the live scanner to populate backend AI recommendations." />
            )}
          </TerminalPanel>
          <TerminalPanel eyebrow="Ranked Intelligence" title="Backend Scoring Matrix">
            <DataTable
              columns={['Stock', 'Sector', 'Rating', 'Profitability', 'Growth', 'Value', 'Momentum', 'Risk', 'Reason']}
              rows={aiRows.map((stock: any) => [
                <strong key={`${stock.symbol}-symbol`}>{stock.symbol}</strong>,
                stock.sector || '-',
                stock.ai_rating || '-',
                stock.profitability_score ?? stock.final_ai_score ?? '-',
                stock.growth_score ?? '-',
                stock.value_score ?? '-',
                stock.momentum_score ?? '-',
                stock.risk_score ?? '-',
                stock.reasoning || stock.reason || '-',
              ])}
            />
          </TerminalPanel>
        </>
      )}
    </main>
  );
}
