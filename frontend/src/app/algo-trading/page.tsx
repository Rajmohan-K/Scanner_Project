"use client";

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Bot,
  CircleDollarSign,
  Octagon,
  Play,
  RefreshCw,
  ShieldCheck,
  Square,
  Target,
  TrendingUp,
  WalletCards,
} from 'lucide-react';
import {
  AlgoOrder,
  AlgoStatusPayload,
  getAlgoStatus,
  startAlgoTrading,
  stopAlgoTrading,
} from '@/lib/api';
import { DataTable, EmptyState, MetricTile, TerminalPanel } from '@/components/terminal/TerminalPrimitives';
import { useToast } from '@/components/layout/ToastProvider';

const money = (value: unknown) => Number(value || 0).toLocaleString('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 });
const number = (value: unknown, digits = 2) => Number(value || 0).toFixed(digits);

export default function AlgoTradingPage() {
  const toast = useToast();
  const [capital, setCapital] = useState(100000);
  const [maxTrades, setMaxTrades] = useState(3);
  const [maxLoss, setMaxLoss] = useState(2000);
  const [riskPerTrade, setRiskPerTrade] = useState(1);
  const [dummyTrading, setDummyTrading] = useState(true);
  const [status, setStatus] = useState<AlgoStatusPayload | null>(null);
  const [portfolio, setPortfolio] = useState<Record<string, any>>({});
  const [orders, setOrders] = useState<AlgoOrder[]>([]);
  const [trades, setTrades] = useState<any[]>([]);
  const [performance, setPerformance] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const refresh = useCallback(async (silent = true) => {
    try {
      const statusPayload = await getAlgoStatus();
      setStatus(statusPayload);
      setPortfolio(statusPayload.portfolio || {});
      setOrders(statusPayload.orders || []);
      setTrades(statusPayload.trades_today || []);
      setPerformance(statusPayload.performance || {});
      setError('');
    } catch (err: any) {
      const message = err?.response?.data?.message || err?.message || 'Algo service unavailable';
      setError(message);
      if (!silent) toast?.push(message, 'error');
    }
  }, [toast]);

  useEffect(() => {
    refresh(false);
    const timer = window.setInterval(() => refresh(true), 1000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const running = status?.status === 'RUNNING' || status?.status === 'STARTING';
  const activeOrder = orders.find((row) => ['PENDING', 'OPEN', 'PARTIAL_EXIT'].includes(row.status));
  const selected = status?.selected_trade;
  const latestReview = trades[0]?.improvement || null;

  async function start() {
    setBusy(true);
    try {
      await startAlgoTrading({ capital, max_trades: maxTrades, max_loss: maxLoss, risk_per_trade: riskPerTrade, dummy_trading: dummyTrading, real_trading: false });
      toast?.push('Paper algo session started', 'success');
      await refresh();
    } catch (err: any) {
      toast?.push(err?.response?.data?.message || err?.message || 'Unable to start paper algo', 'error');
    } finally {
      setBusy(false);
    }
  }

  async function stop(reason = 'Stopped by user') {
    setBusy(true);
    try {
      await stopAlgoTrading(reason);
      toast?.push(reason === 'Emergency stop' ? 'Emergency stop completed' : 'Paper algo stopped', 'warning');
      await refresh();
    } catch (err: any) {
      toast?.push(err?.response?.data?.message || err?.message || 'Unable to stop paper algo', 'error');
    } finally {
      setBusy(false);
    }
  }

  const chartPoints = useMemo(() => {
    const snapshots = Array.isArray(performance.snapshots) ? performance.snapshots.slice(-60) : [];
    if (!snapshots.length) return '';
    const values = snapshots.map((row: any) => Number(row.pnl || 0));
    const low = Math.min(...values, 0);
    const high = Math.max(...values, 0);
    const span = Math.max(high - low, 1);
    return values.map((value: number, index: number) => {
      const x = snapshots.length === 1 ? 0 : (index / (snapshots.length - 1)) * 100;
      const y = 48 - ((value - low) / span) * 44;
      return `${x},${y}`;
    }).join(' ');
  }, [performance.snapshots]);

  const orderRows = orders.map((order) => [
    new Date(order.created_at).toLocaleTimeString('en-IN'),
    <strong key="symbol">{order.symbol}</strong>,
    <span key="side" className={`status-pill ${order.side === 'BUY' ? 'positive' : 'negative'}`}>{order.side}</span>,
    `${order.remaining_quantity}/${order.quantity}`,
    money(order.entry_price), money(order.current_price), money(order.stop_loss), money(order.trailing_stop_loss), money(order.target),
    <span key="status" className="status-pill">{order.status}</span>,
    <strong key="pnl" className={order.pnl >= 0 ? 'positive' : 'negative'}>{money(order.pnl)}</strong>,
    order.exit_reason || '-', `${number(order.confidence)}%`, order.strategy_reason || '-',
  ]);

  return (
    <main className="algo-page">
      <div className="algo-titlebar">
        <div>
          <p className="terminal-eyebrow">Automated execution console</p>
          <h1>Realtime Algo Trading</h1>
        </div>
        <div className="algo-mode-strip">
          <span className="algo-chip is-paper"><ShieldCheck size={14} /> PAPER MODE ACTIVE</span>
          <span className="algo-chip is-locked"><Octagon size={14} /> REAL ORDERS DISABLED</span>
          <span className={`algo-chip ${status?.kotak_neo_connected ? 'is-live' : 'is-muted'}`}>KOTAK NEO {status?.kotak_neo_connected ? 'CONNECTED' : 'NOT CONNECTED'}</span>
          <span className={`algo-chip ${status?.market_data?.connected ? 'is-live' : 'is-stale'}`}>LIVE DATA {status?.market_data?.connected ? 'CONNECTED' : 'STALE'}</span>
        </div>
      </div>

      {error && <div className="algo-alert"><AlertTriangle size={16} /> {error}</div>}

      <section className="algo-control-band">
        <div className="algo-status-block">
          <span>Algo status</span>
          <strong className={running ? 'positive' : ''}>{status?.status || 'IDLE'}</strong>
          <small>{status?.session?.stop_reason || `Yahoo age ${number(status?.market_data?.age_seconds, 1)}s`}</small>
        </div>
        <label><span>Trading capital</span><input type="number" min="1000" step="1000" value={capital} disabled={running} onChange={(event) => setCapital(Number(event.target.value))} /></label>
        <label><span>Max trades/day</span><input type="number" min="1" max="20" value={maxTrades} disabled={running} onChange={(event) => setMaxTrades(Number(event.target.value))} /></label>
        <label><span>Max loss/day</span><input type="number" min="100" step="100" value={maxLoss} disabled={running} onChange={(event) => setMaxLoss(Number(event.target.value))} /></label>
        <label><span>Risk/trade %</span><input type="number" min="0.1" max="5" step="0.1" value={riskPerTrade} disabled={running} onChange={(event) => setRiskPerTrade(Number(event.target.value))} /></label>
        <label className="algo-toggle"><input type="checkbox" checked={dummyTrading} disabled={running} onChange={(event) => setDummyTrading(event.target.checked)} /><span>Dummy trading</span></label>
        <label className="algo-toggle is-disabled"><input type="checkbox" checked={false} disabled /><span>Real trading</span></label>
        <div className="algo-control-actions">
          <button className="btn-primary" type="button" disabled={running || busy || !dummyTrading} onClick={start}><Play size={15} /> Start</button>
          <button className="btn-secondary" type="button" disabled={!running || busy} onClick={() => stop()}><Square size={14} /> Stop</button>
          <button className="btn-danger" type="button" disabled={!running || busy} onClick={() => stop('Emergency stop')}><Octagon size={15} /> Emergency Stop</button>
          <button className="icon-button" type="button" title="Refresh algo data" onClick={() => refresh(false)}><RefreshCw size={15} /></button>
        </div>
      </section>

      <div className="algo-primary-grid">
        <TerminalPanel eyebrow="Selection" title="Best Trade Selected" className="algo-selection-panel">
          {selected ? (
            <div className="algo-selected-trade">
              <div><span>Symbol</span><strong>{selected.symbol}</strong></div>
              <div><span>Side</span><strong className={selected.side === 'BUY' ? 'positive' : 'negative'}>{selected.side}</strong></div>
              <div><span>Confidence</span><strong>{number(selected.confidence)}%</strong></div>
              <div><span>Selection score</span><strong>{number(selected.selection_score)}</strong></div>
              <div><span>Entry</span><strong>{money(selected.entry_price)}</strong></div>
              <div><span>Stop loss</span><strong>{money(selected.stop_loss)}</strong></div>
              <div><span>Target</span><strong>{money(selected.target)}</strong></div>
              <div><span>Risk/reward</span><strong>{number(selected.risk_reward)}x</strong></div>
              <p>{selected.strategy_reason}</p>
            </div>
          ) : <EmptyState title="Awaiting qualified setup" body="No fresh high-confidence watchlist trade currently passes every safety gate." />}
        </TerminalPanel>

        <TerminalPanel eyebrow="Execution" title="Live Position">
          {activeOrder ? (
            <div className="algo-live-position">
              <div className="algo-position-head"><strong>{activeOrder.symbol}</strong><span className="status-pill">{activeOrder.status}</span></div>
              <div className="algo-position-pnl"><span>Unrealized P/L</span><strong className={activeOrder.pnl >= 0 ? 'positive' : 'negative'}>{money(activeOrder.pnl)}</strong></div>
              <dl>
                <div><dt>Side / Qty</dt><dd>{activeOrder.side} / {activeOrder.remaining_quantity}</dd></div>
                <div><dt>Entry</dt><dd>{money(activeOrder.entry_price)}</dd></div>
                <div><dt>Current</dt><dd>{money(activeOrder.current_price)}</dd></div>
                <div><dt>Trailing SL</dt><dd>{money(activeOrder.trailing_stop_loss)}</dd></div>
                <div><dt>Target</dt><dd>{money(activeOrder.target)}</dd></div>
              </dl>
            </div>
          ) : <EmptyState title="No open paper position" body="The engine is monitoring qualified suggestions." />}
        </TerminalPanel>
      </div>

      <section className="algo-metrics-grid">
        <MetricTile label="Capital allocated" value={money(portfolio.capital_allocated)} icon={WalletCards} />
        <MetricTile label="Available funds" value={money(portfolio.available_funds)} icon={CircleDollarSign} tone="info" />
        <MetricTile label="Used margin" value={money(portfolio.used_margin)} icon={Target} />
        <MetricTile label="Open / Closed" value={`${portfolio.open_positions || 0} / ${portfolio.closed_positions || 0}`} icon={Bot} />
        <MetricTile label="Wins / Losses" value={`${portfolio.winning_trades || 0} / ${portfolio.losing_trades || 0}`} icon={TrendingUp} tone={(portfolio.winning_trades || 0) >= (portfolio.losing_trades || 0) ? 'good' : 'bad'} />
        <MetricTile label="Realized P/L" value={money(portfolio.realized_pnl)} tone={(portfolio.realized_pnl || 0) >= 0 ? 'good' : 'bad'} />
        <MetricTile label="Unrealized P/L" value={money(portfolio.unrealized_pnl)} tone={(portfolio.unrealized_pnl || 0) >= 0 ? 'good' : 'bad'} />
        <MetricTile label="Charges estimate" value={money(portfolio.charges)} />
        <MetricTile label="Net P/L" value={money(portfolio.net_pnl)} tone={(portfolio.net_pnl || 0) >= 0 ? 'good' : 'bad'} />
      </section>

      <TerminalPanel eyebrow="Paper order book" title="Orders">
        <DataTable
          columns={['Time', 'Symbol', 'Side', 'Qty', 'Entry', 'Current', 'Stoploss', 'Trailing SL', 'Target', 'Status', 'P/L', 'Exit reason', 'Confidence', 'Strategy reason']}
          rows={orderRows}
          emptyTitle="No paper orders today"
          emptyBody="Orders appear here after a fresh suggestion clears all execution gates."
        />
      </TerminalPanel>

      <div className="algo-secondary-grid">
        <TerminalPanel eyebrow="Daily performance" title="P/L Chart">
          {chartPoints ? (
            <div className="algo-chart">
              <div><span>Net P/L</span><strong className={(portfolio.net_pnl || 0) >= 0 ? 'positive' : 'negative'}>{money(portfolio.net_pnl)}</strong></div>
              <svg viewBox="0 0 100 52" preserveAspectRatio="none" role="img" aria-label="Intraday net profit and loss chart">
                <line x1="0" y1="48" x2="100" y2="48" />
                <polyline points={chartPoints} />
              </svg>
            </div>
          ) : <EmptyState title="No P/L movement yet" body="The chart starts with the first paper execution update." />}
        </TerminalPanel>

        <TerminalPanel eyebrow="Post-trade review" title="Improvement Suggestions">
          {latestReview ? (
            <div className="algo-review-list">
              <div><span>Selection</span><p>{latestReview.selection}</p></div>
              <div><span>Outcome</span><p>{latestReview.outcome}</p></div>
              <div><span>Stop / target</span><p>{latestReview.stop_assessment}. {latestReview.target_assessment}.</p></div>
              <div><span>Volume</span><p>{latestReview.volume_confirmation}</p></div>
              <div><span>Next trade</span><p>{latestReview.next_improvement}</p></div>
              <div><span>Avoid similar setup</span><strong>{latestReview.avoid_similar_setup ? 'YES' : 'NO'}</strong></div>
            </div>
          ) : <EmptyState title="No closed-trade review" body="A structured review is generated after each paper trade closes." />}
        </TerminalPanel>
      </div>
    </main>
  );
}
