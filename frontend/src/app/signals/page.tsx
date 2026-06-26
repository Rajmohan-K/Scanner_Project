"use client";

import React, { useMemo, useState } from 'react';
import useSWR from 'swr';
import { getSignals } from '@/lib/api';
import { PageHero, TerminalPanel } from '@/components/terminal/TerminalPrimitives';
import { Filter, Percent, Shield, TrendingUp, Trophy, Watch } from 'lucide-react';
import { useToast } from '@/components/layout/ToastProvider';

function formatNumber(value: unknown, digits = 2) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : '-';
}

function formatCurrency(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? `₹${number.toFixed(2)}` : '-';
}

function statusTone(status?: string) {
  const s = String(status || '').toUpperCase();
  if (s.includes('HIT') || s === 'ACTIVE' || s.includes('TRAILING') || s.includes('WIN')) return 'good';
  if (s.includes('STOP') || s.includes('LOSS') || s === 'CLOSED' || s.includes('LOSE')) return 'bad';
  return 'warn';
}

function errorMessage(error: unknown) {
  if (!error) return 'Unable to load signals.';
  if (error instanceof Error) return error.message;
  if (typeof error === 'string') return error;
  if (typeof error === 'object' && 'message' in error) return String((error as { message?: unknown }).message || 'Unable to load signals.');
  return 'Unable to load signals.';
}

export default function SignalHistoryPage() {
  const toast = useToast();
  const { data, error, isLoading } = useSWR('/api/signals', () => getSignals(), {
    refreshInterval: 2000, // Poll every 2 seconds for real-time tick performance
    dedupingInterval: 1000,
  });

  const activeSignals = data?.active || [];
  const historySignals = data?.history || [];

  // Combine both for dashboard stats and filtering
  const allSignals = useMemo(() => {
    return [
      ...activeSignals.map((s: any) => ({ ...s, is_active_signal: true })),
      ...historySignals.map((s: any) => ({ ...s, is_active_signal: false })),
    ];
  }, [activeSignals, historySignals]);

  // Filters state
  const [filterDirection, setFilterDirection] = useState('all'); // all, BUY, SELL
  const [filterStatus, setFilterStatus] = useState('all'); // all, active, closed
  const [filterTimeframe, setFilterTimeframe] = useState('all'); // all, intraday, swing
  const [filterPeriod, setFilterPeriod] = useState('all'); // all, today, week

  // Filtered list
  const filteredSignals = useMemo(() => {
    return allSignals.filter((sig) => {
      // 1. Direction Filter
      if (filterDirection !== 'all' && sig.direction !== filterDirection) return false;

      // 2. Status Filter
      if (filterStatus === 'active' && !sig.is_active_signal) return false;
      if (filterStatus === 'closed' && sig.is_active_signal) return false;

      // 3. Timeframe Filter (Intraday vs Swing)
      const isSwing = String(sig.initial_reason || '').toLowerCase().includes('swing') || 
                      String(sig.reason || '').toLowerCase().includes('swing');
      if (filterTimeframe === 'intraday' && isSwing) return false;
      if (filterTimeframe === 'swing' && !isSwing) return false;

      // 4. Period Filter (Today vs Week)
      if (filterPeriod !== 'all') {
        const sigTime = sig.suggested_timestamp ? sig.suggested_timestamp * 1000 : Date.now();
        const diffMs = Date.now() - sigTime;
        if (filterPeriod === 'today' && diffMs > 24 * 60 * 60 * 1000) return false;
        if (filterPeriod === 'week' && diffMs > 7 * 24 * 60 * 60 * 1000) return false;
      }

      return true;
    });
  }, [allSignals, filterDirection, filterStatus, filterTimeframe, filterPeriod]);

  // Dashboard Stats Calculations (Rule 6)
  const stats = useMemo(() => {
    const closed = historySignals;
    const total = allSignals.length;
    const active = activeSignals.length;
    const closedCount = closed.length;

    let wins = 0;
    let losses = 0;
    let sumWins = 0;
    let sumLosses = 0;
    let bestGain = -999;
    let worstGain = 999;
    let bestSig: any = null;
    let worstSig: any = null;

    closed.forEach((sig: any) => {
      const res = sig.current_result || 0.0;
      if (res > 0) {
        wins += 1;
        sumWins += res;
      } else {
        losses += 1;
        sumLosses += Math.abs(res);
      }

      if (res > bestGain) {
        bestGain = res;
        bestSig = sig;
      }
      if (res < worstGain) {
        worstGain = res;
        worstSig = sig;
      }
    });

    const winRate = closedCount > 0 ? (wins / closedCount) * 100 : 0.0;
    const avgGain = wins > 0 ? sumWins / wins : 0.0;
    const avgLoss = losses > 0 ? sumLosses / losses : 0.0;
    const profitFactor = sumLosses > 0 ? sumWins / sumLosses : sumWins > 0 ? 99.9 : 0.0;

    return {
      total,
      active,
      closed: closedCount,
      wins,
      losses,
      winRate,
      avgGain,
      avgLoss,
      profitFactor,
      bestSig,
      worstSig,
    };
  }, [allSignals, activeSignals, historySignals]);

  return (
    <main className="terminal-viewport signals-viewport">
      <PageHero 
        eyebrow="SIGNAL JOURNAL"
        title="Signal Lifecycle terminal" 
        description="V50 Signal Integrity engine / Permanent suggestions tracking & evaluation" 
      />

      {/* Accuracy Dashboard (Rule 6) */}
      <div className="terminal-dashboard-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '10px', marginBottom: '15px' }}>
        <div className="dashboard-card">
          <div className="card-label"><Trophy size={14} style={{ color: 'var(--accent)', marginRight: '4px' }} /> Win Rate (Closed)</div>
          <div className="card-value value--good">{formatNumber(stats.winRate, 1)}%</div>
          <div className="card-sub">{stats.wins} Wins / {stats.losses} Losses</div>
        </div>
        <div className="dashboard-card">
          <div className="card-label"><Percent size={14} style={{ color: 'var(--accent)', marginRight: '4px' }} /> Profit Factor</div>
          <div className="card-value">{formatNumber(stats.profitFactor, 2)}x</div>
          <div className="card-sub">Ratio of Wins to Losses</div>
        </div>
        <div className="dashboard-card">
          <div className="card-label"><TrendingUp size={14} style={{ color: 'var(--accent)', marginRight: '4px' }} /> Avg Gain / Loss</div>
          <div className="card-value" style={{ display: 'flex', gap: '8px', fontSize: '1.2rem' }}>
            <span className="value--good">+{formatNumber(stats.avgGain, 2)}%</span>
            <span className="value--bad">-{formatNumber(stats.avgLoss, 2)}%</span>
          </div>
          <div className="card-sub">Hold performance averages</div>
        </div>
        <div className="dashboard-card">
          <div className="card-label"><Shield size={14} style={{ color: 'var(--accent)', marginRight: '4px' }} /> Total Signals</div>
          <div className="card-value">{stats.total}</div>
          <div className="card-sub">{stats.active} Active / {stats.closed} Closed</div>
        </div>
        <div className="dashboard-card" title={stats.bestSig ? `${stats.bestSig.symbol}: +${stats.bestSig.current_result}%` : ''}>
          <div className="card-label">Best Signal</div>
          <div className="card-value value--good" style={{ fontSize: '1.05rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {stats.bestSig ? `${stats.bestSig.symbol.split('.')[0]} (+${formatNumber(stats.bestSig.current_result)}%)` : '-'}
          </div>
          <div className="card-sub">Highest closed gain</div>
        </div>
        <div className="dashboard-card" title={stats.worstSig ? `${stats.worstSig.symbol}: ${stats.worstSig.current_result}%` : ''}>
          <div className="card-label">Worst Signal</div>
          <div className="card-value value--bad" style={{ fontSize: '1.05rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {stats.worstSig ? `${stats.worstSig.symbol.split('.')[0]} (${formatNumber(stats.worstSig.current_result)}%)` : '-'}
          </div>
          <div className="card-sub">Largest closed drawdown</div>
        </div>
      </div>

      {/* Interactive Signal Filters (Rule 5) */}
      <TerminalPanel title="Signal Filters">
        <div className="filters-row" style={{ display: 'flex', gap: '15px', padding: '5px', flexWrap: 'wrap' }}>
          <div className="filter-group">
            <label style={{ marginRight: '6px', fontSize: '0.75rem', color: 'var(--muted)', fontWeight: 'bold' }}>DIRECTION:</label>
            <select className="api-target-select" value={filterDirection} onChange={(e) => setFilterDirection(e.target.value)}>
              <option value="all">ALL DIRECTIONS</option>
              <option value="BUY">BUY SIGNALS</option>
              <option value="SELL">SELL SIGNALS</option>
            </select>
          </div>
          <div className="filter-group">
            <label style={{ marginRight: '6px', fontSize: '0.75rem', color: 'var(--muted)', fontWeight: 'bold' }}>STATUS:</label>
            <select className="api-target-select" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
              <option value="all">ALL STATUSES</option>
              <option value="active">ACTIVE SIGNALS</option>
              <option value="closed">CLOSED SIGNALS</option>
            </select>
          </div>
          <div className="filter-group">
            <label style={{ marginRight: '6px', fontSize: '0.75rem', color: 'var(--muted)', fontWeight: 'bold' }}>TIMEFRAME:</label>
            <select className="api-target-select" value={filterTimeframe} onChange={(e) => setFilterTimeframe(e.target.value)}>
              <option value="all">ALL TIMEFRAMES</option>
              <option value="intraday">INTRADAY CANDIDATES</option>
              <option value="swing">SWING CANDIDATES</option>
            </select>
          </div>
          <div className="filter-group">
            <label style={{ marginRight: '6px', fontSize: '0.75rem', color: 'var(--muted)', fontWeight: 'bold' }}>DATE RANGE:</label>
            <select className="api-target-select" value={filterPeriod} onChange={(e) => setFilterPeriod(e.target.value)}>
              <option value="all">ALL DATES</option>
              <option value="today">TODAY ONLY</option>
              <option value="week">THIS WEEK</option>
            </select>
          </div>
        </div>
      </TerminalPanel>

      {/* Signals Table Panel */}
      <TerminalPanel title={`Signal tracking history (${filteredSignals.length} records)`}>
        {isLoading && allSignals.length === 0 ? (
          <div className="terminal-loading">Syncing Signal records from V50 Engine...</div>
        ) : error ? (
          <div className="terminal-error">{errorMessage(error)}</div>
        ) : filteredSignals.length === 0 ? (
          <div className="terminal-empty">No Signal records found matching current filters.</div>
        ) : (
          <div className="terminal-table-container">
            <div className="terminal-table-header" style={{
              display: 'grid',
              gridTemplateColumns: '150px 100px 100px 100px 100px 100px 100px 110px 100px 110px 90px 1fr',
              gap: '8px',
              padding: '8px',
              borderBottom: '1px solid var(--border)',
              fontWeight: 'bold',
              fontSize: '0.75rem',
              color: 'var(--muted)',
              textTransform: 'uppercase',
              whiteSpace: 'nowrap'
            }}>
              <span>Signal ID</span>
              <span>Stock</span>
              <span>Suggested</span>
              <span>Sug. Price</span>
              <span>Current</span>
              <span>Max Gain</span>
              <span>Max DD</span>
              <span>Status</span>
              <span>Current P/L</span>
              <span>Duration</span>
              <span>Provider</span>
              <span>Reason / Setup</span>
            </div>
            <div className="terminal-table-body">
              {filteredSignals.map((sig) => {
                const plVal = sig.is_active_signal ? sig.current_pl_percent : sig.current_result;
                
                return (
                  <article key={sig.signal_id} className="terminal-table-row" style={{
                    display: 'grid',
                    gridTemplateColumns: '150px 100px 100px 100px 100px 100px 100px 110px 100px 110px 90px 1fr',
                    gap: '8px',
                    padding: '8px',
                    borderBottom: '1px dashed var(--border)',
                    fontSize: '0.8rem',
                    alignItems: 'center'
                  }}>
                    <strong style={{ color: 'var(--accent)' }}>{sig.signal_id}</strong>
                    <strong style={{ display: 'flex', flexDirection: 'column' }}>
                      <span>{sig.symbol.split('.')[0]}</span>
                      <small style={{ fontSize: '0.65rem', color: 'var(--muted)' }}>{sig.symbol}</small>
                    </strong>
                    <span>{sig.suggested_at}</span>
                    <span>{formatCurrency(sig.suggested_price || sig.entry_price)}</span>
                    <span>{formatCurrency(sig.current_price)}</span>
                    <span className="positive">+{formatNumber(sig.max_gain_percent || sig.max_gain)}%</span>
                    <span className="negative">-{formatNumber(sig.max_drawdown || sig.max_drawdown_percent)}%</span>
                    <span className={`pill pill-${statusTone(sig.status || sig.final_status)}`}>
                      {sig.status || sig.final_status}
                    </span>
                    <span className={plVal >= 0 ? 'positive' : 'negative'}>
                      {plVal >= 0 ? '+' : ''}{formatNumber(plVal)}%
                    </span>
                    <span>{sig.time_active || sig.duration || '0s'}</span>
                    <span style={{ fontSize: '0.72rem', color: 'var(--muted)', textTransform: 'uppercase' }}>{sig.provider}</span>
                    <span style={{ fontSize: '0.75rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={sig.reason || sig.latest_analysis}>
                      {sig.reason || sig.latest_analysis || 'No Setup'}
                    </span>
                  </article>
                );
              })}
            </div>
          </div>
        )}
      </TerminalPanel>
    </main>
  );
}
