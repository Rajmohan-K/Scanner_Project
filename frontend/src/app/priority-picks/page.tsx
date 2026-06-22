"use client";
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Bell, BellPlus, Download, PlayCircle, Target, Trash2, Trophy, X } from 'lucide-react';
import { DataTable, MetricTile, PageHero, TerminalPanel, Toolbar } from '@/components/terminal/TerminalPrimitives';
import { extractStockRows, getScanDetail, getV20Quote, listScans, normalizeStockRow, sendTelegramStockAlert } from '@/lib/api';
import { readGrowwResults } from '@/lib/growwIntraday';
import { buildPriorityRows, PriorityHorizon, PRIORITY_CANDIDATES_EVENT, prioritySymbol, readPriorityCandidateRows } from '@/lib/priorityPicks';
import { useToast } from '@/components/layout/ToastProvider';
import { addStocksToLiveMonitor } from '@/lib/liveMonitor';
import { hydrateRowsWithUnifiedAnalysis } from '@/lib/unifiedAnalysis';

type PrioritySettings = {
  telegramEnabled: boolean;
  alertFound: boolean;
  alertTarget: boolean;
  alertStoploss: boolean;
  minProfitPct: number;
  limit: number;
};

type TrackedPriorityRow = any & {
  key: string;
  horizon: PriorityHorizon;
  status: 'active';
  found_at: string;
  suggested_entry_time: string;
  last_price?: number;
  last_checked?: string;
  lifecycle_reason?: string;
};

type PriorityHistoryRow = TrackedPriorityRow & {
  status: 'target_hit' | 'stoploss_hit' | 'removed';
  closed_at: string;
  close_price?: number;
  close_reason: string;
};

const ACTIVE_KEY = 'priority-picks-active-v1';
const HISTORY_KEY = 'priority-picks-history-v1';
const SETTINGS_KEY = 'priority-picks-settings-v1';
const defaultSettings: PrioritySettings = {
  telegramEnabled: false,
  alertFound: true,
  alertTarget: true,
  alertStoploss: true,
  minProfitPct: 3,
  limit: 5,
};

function readJson<T>(key: string, fallback: T): T {
  if (typeof window === 'undefined') return fallback;
  try {
    const parsed = JSON.parse(window.localStorage.getItem(key) || '');
    return parsed || fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key: string, value: unknown) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(key, JSON.stringify(value));
}

function rowKey(row: any, horizon: PriorityHorizon) {
  return `${horizon}:${prioritySymbol(row)}`;
}

function nowIso() {
  return new Date().toISOString();
}

function formatDateTime(value?: string) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'medium' });
}

function formatPrice(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return '-';
  return numeric.toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

function formatPct(value: unknown) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${numeric.toFixed(2)}%` : '-';
}

function reasonText(row: any) {
  return row.detailed_priority_reason || row.priority_reason || row.reason || row.explanation || row.trade_reason || row.recommendation_reason || 'No detailed reason available yet.';
}

function normalizeTrackedRow(row: any, horizon: PriorityHorizon): TrackedPriorityRow {
  const timestamp = row.suggested_entry_time || row.generated_at || row.last_updated || nowIso();
  return {
    ...row,
    key: rowKey(row, horizon),
    symbol: prioritySymbol(row),
    horizon,
    status: 'active',
    found_at: nowIso(),
    suggested_entry_time: timestamp,
    lifecycle_reason: 'Active priority candidate from latest scan sources',
  };
}

function targetForOutcome(row: TrackedPriorityRow) {
  return Number(row.target1 || row.target_1 || row.target2 || row.target_2 || 0);
}

function stopForOutcome(row: TrackedPriorityRow) {
  return Number(row.stop_loss || row.stoploss || 0);
}

function isSellSetup(row: TrackedPriorityRow) {
  return /sell|short/i.test(`${row.action || ''} ${row.signal || ''} ${row.trade_type || ''}`);
}

function outcomeForPrice(row: TrackedPriorityRow, livePrice: number) {
  const target = targetForOutcome(row);
  const stop = stopForOutcome(row);
  if (!livePrice || (!target && !stop)) return null;
  if (isSellSetup(row)) {
    if (stop && livePrice >= stop) return { status: 'stoploss_hit' as const, reason: `Sell setup stoploss hit at ${formatPrice(livePrice)}` };
    if (target && livePrice <= target) return { status: 'target_hit' as const, reason: `Sell setup target hit at ${formatPrice(livePrice)}` };
    return null;
  }
  if (stop && livePrice <= stop) return { status: 'stoploss_hit' as const, reason: `Stoploss hit at ${formatPrice(livePrice)}` };
  if (target && livePrice >= target) return { status: 'target_hit' as const, reason: `Target hit at ${formatPrice(livePrice)}` };
  return null;
}

async function collectScanRows(pattern: RegExp, horizon: 'intraday' | 'swing') {
  const list = await listScans();
  const scans = (list?.scans || [])
    .filter((scan: any) => {
      const text = `${scan.scan_family || ''} ${scan.scanner_bucket || ''} ${scan.pipeline_stage || ''} ${scan.scan_mode || scan.scan_type || scan.type || ''}`.toLowerCase();
      return (scan.scan_id || scan.id) && pattern.test(text);
    })
    .slice(0, 8);
  const details = await Promise.allSettled(scans.map((scan: any) => getScanDetail(scan.scan_id || scan.id)));
  return details.flatMap((detail) => (
    detail.status === 'fulfilled'
      ? extractStockRows(detail.value, { horizon, actionableOnly: false, source: 'best' }).map(normalizeStockRow)
      : []
  ));
}

export default function PriorityPicksPage() {
  const toast = useToast();
  const [activeRows, setActiveRows] = useState<TrackedPriorityRow[]>([]);
  const [historyRows, setHistoryRows] = useState<PriorityHistoryRow[]>([]);
  const [settings, setSettings] = useState<PrioritySettings>(defaultSettings);
  const [query, setQuery] = useState('');
  const [selectedKey, setSelectedKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [sourceMessage, setSourceMessage] = useState('Waiting for priority sources.');
  const activeRowsRef = useRef<TrackedPriorityRow[]>([]);
  const historyRowsRef = useRef<PriorityHistoryRow[]>([]);
  const settingsRef = useRef<PrioritySettings>(defaultSettings);
  const quoteRefreshingRef = useRef(false);
  const alertKeysRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const active = readJson<TrackedPriorityRow[]>(ACTIVE_KEY, []);
    const history = readJson<PriorityHistoryRow[]>(HISTORY_KEY, []);
    const savedSettings = { ...defaultSettings, ...readJson<Partial<PrioritySettings>>(SETTINGS_KEY, {}) };
    activeRowsRef.current = active;
    historyRowsRef.current = history;
    settingsRef.current = savedSettings;
    setActiveRows(active);
    setHistoryRows(history);
    setSettings(savedSettings);
  }, []);

  useEffect(() => {
    activeRowsRef.current = activeRows;
    writeJson(ACTIVE_KEY, activeRows);
  }, [activeRows]);

  useEffect(() => {
    historyRowsRef.current = historyRows;
    writeJson(HISTORY_KEY, historyRows);
  }, [historyRows]);

  useEffect(() => {
    settingsRef.current = settings;
    writeJson(SETTINGS_KEY, settings);
  }, [settings]);

  async function maybeSendTelegram(row: TrackedPriorityRow | PriorityHistoryRow, event: 'found' | 'target_hit' | 'stoploss_hit', status: string) {
    const current = settingsRef.current;
    const eventEnabled =
      (event === 'found' && current.alertFound) ||
      (event === 'target_hit' && current.alertTarget) ||
      (event === 'stoploss_hit' && current.alertStoploss);
    if (!current.telegramEnabled || !eventEnabled) return;
    const key = `${row.key}:${event}:${row.closed_at || row.found_at}`;
    if (alertKeysRef.current.has(key)) return;
    alertKeysRef.current.add(key);
    try {
      await sendTelegramStockAlert({
        symbol: row.symbol,
        status,
        telegram_category: row.horizon === 'swing' ? 'Swing Priority' : 'Intraday Priority',
        live_price: row.last_price ?? row.live_price ?? row.current_price,
        entry_price: row.entry_price ?? row.entry,
        stop_loss: row.stop_loss ?? row.stoploss,
        target1: row.target1 ?? row.target_1,
        target2: row.target2 ?? row.target_2,
        suggested_entry_time: row.suggested_entry_time,
      });
    } catch (error: any) {
      toast?.push(`Telegram ${event.replace('_', ' ')} alert failed for ${row.symbol}: ${error?.message || 'check settings'}`, 'error');
    }
  }

  function updateSettings(patch: Partial<PrioritySettings>) {
    setSettings((current) => ({ ...current, ...patch }));
  }

  function upsertPriorityRows(rows: TrackedPriorityRow[]) {
    if (!rows.length) return;
    setActiveRows((current) => {
      const now = Date.now();
      const recentClosed = new Map(
        historyRowsRef.current
          .filter((row) => now - new Date(row.closed_at).getTime() < 30 * 60 * 1000)
          .map((row) => [row.key, row]),
      );
      const byKey = new Map(current.map((row) => [row.key, row]));
      const foundRows: TrackedPriorityRow[] = [];
      rows.forEach((row) => {
        if (recentClosed.has(row.key)) return;
        const existing = byKey.get(row.key);
        if (existing) {
          byKey.set(row.key, {
            ...existing,
            ...row,
            found_at: existing.found_at,
            suggested_entry_time: existing.suggested_entry_time || row.suggested_entry_time,
            status: 'active',
          });
        } else {
          byKey.set(row.key, row);
          foundRows.push(row);
        }
      });
      foundRows.forEach((row) => maybeSendTelegram(row, 'found', `Priority stock found: ${row.symbol}`));
      if (foundRows.length) toast?.push(`${foundRows.length} new priority pick(s) added`, 'success');
      return Array.from(byKey.values()).sort((a, b) => Number(b.priority_profit_pct || 0) - Number(a.priority_profit_pct || 0));
    });
  }

  async function loadPrioritySources() {
    if (loading) return;
    setLoading(true);
    try {
      const groww = readGrowwResults();
      const externalCandidates = readPriorityCandidateRows();
      const externalIntraday = externalCandidates.filter((row: any) => /intraday|groww|premarket|open/i.test(`${row.priority_horizon || row.horizon || row.source_name || ''}`));
      const externalSwing = externalCandidates.filter((row: any) => /swing/i.test(`${row.priority_horizon || row.horizon || row.source_name || ''}`));
      const [intradayResult, swingResult] = await Promise.allSettled([
        collectScanRows(/intraday|premarket|market[- ]?open|open[- ]?confirmation|groww|custom/, 'intraday'),
        collectScanRows(/swing|positional|multi[- ]?day|custom/, 'swing'),
      ]);
      const intradayRows = intradayResult.status === 'fulfilled' ? intradayResult.value : [];
      const swingRows = swingResult.status === 'fulfilled' ? swingResult.value : [];
      const unifiedIntraday = await hydrateRowsWithUnifiedAnalysis([...(groww.priorityRows || []), ...(groww.rows || []), ...intradayRows, ...externalIntraday], 'intraday', 200);
      const unifiedSwing = await hydrateRowsWithUnifiedAnalysis([...swingRows, ...externalSwing], 'swing', 200);
      const intradayPriority = buildPriorityRows(unifiedIntraday, {
        horizon: 'intraday',
        includeUnknown: true,
        minProfitPct: settingsRef.current.minProfitPct,
        limit: settingsRef.current.limit,
        sourceName: 'Intraday Sources',
      }).map((row) => normalizeTrackedRow(row, 'intraday'));
      const swingPriority = buildPriorityRows(unifiedSwing, {
        horizon: 'swing',
        includeUnknown: true,
        minProfitPct: settingsRef.current.minProfitPct,
        limit: settingsRef.current.limit,
        sourceName: 'Swing Sources',
      }).map((row) => normalizeTrackedRow(row, 'swing'));
      const qualified = [...intradayPriority, ...swingPriority];
      const refreshedKeys = new Set([...unifiedIntraday.map((row: any) => rowKey(row, 'intraday')), ...unifiedSwing.map((row: any) => rowKey(row, 'swing'))]);
      const qualifiedKeys = new Set(qualified.map((row) => row.key));
      setActiveRows((current) => current.filter((row) => !refreshedKeys.has(row.key) || qualifiedKeys.has(row.key)));
      upsertPriorityRows(qualified);
      setSourceMessage(`${intradayPriority.length} intraday and ${swingPriority.length} swing priority picks qualified from latest scan sources.`);
    } catch (error: any) {
      setSourceMessage(error?.message || 'Unable to refresh priority sources');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPrioritySources();
    const timer = window.setInterval(loadPrioritySources, 3000);
    window.addEventListener(PRIORITY_CANDIDATES_EVENT, loadPrioritySources);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener(PRIORITY_CANDIDATES_EVENT, loadPrioritySources);
    };
  }, []);

  function archiveRows(rows: PriorityHistoryRow[]) {
    if (!rows.length) return;
    rows.forEach((row) => {
      if (row.status === 'target_hit') maybeSendTelegram(row, 'target_hit', `${row.symbol} hit target`);
      if (row.status === 'stoploss_hit') maybeSendTelegram(row, 'stoploss_hit', `${row.symbol} hit stoploss`);
    });
    setHistoryRows((current) => [...rows, ...current].slice(0, 500));
  }

  async function refreshQuotes() {
    const rows = activeRowsRef.current;
    if (!rows.length || quoteRefreshingRef.current) return;
    quoteRefreshingRef.current = true;
    try {
      type QuoteUpdate = { key: string; livePrice?: number; checkedAt: string };
      const quoteRows = await Promise.allSettled(rows.map(async (row): Promise<QuoteUpdate> => {
        const payload = await getV20Quote(row.symbol);
        const quote = payload?.quote || {};
        const live = Number(quote.current_price ?? quote.regularMarketPrice ?? quote.price ?? quote.last_close ?? row.last_price ?? 0);
        return {
          key: row.key,
          livePrice: Number.isFinite(live) && live > 0 ? Math.round(live * 100) / 100 : undefined,
          checkedAt: nowIso(),
        };
      }));
      const fulfilledQuoteRows = quoteRows.filter((item): item is PromiseFulfilledResult<QuoteUpdate> => item.status === 'fulfilled');
      const updates = new Map(fulfilledQuoteRows.map((item) => [item.value.key, item.value]));
      const closedRows: PriorityHistoryRow[] = [];
      setActiveRows((current) => {
        const next = current.map((row) => {
          const update = updates.get(row.key);
          if (!update?.livePrice) return row;
          const enriched = { ...row, last_price: update.livePrice, live_price: update.livePrice, last_checked: update.checkedAt };
          const outcome = outcomeForPrice(enriched, update.livePrice);
          if (!outcome) return enriched;
          closedRows.push({
            ...enriched,
            status: outcome.status,
            closed_at: update.checkedAt,
            close_price: update.livePrice,
            close_reason: outcome.reason,
          });
          return enriched;
        });
        const closedKeys = new Set(closedRows.map((row) => row.key));
        return next.filter((row) => !closedKeys.has(row.key));
      });
      if (closedRows.length) archiveRows(closedRows);
    } finally {
      quoteRefreshingRef.current = false;
    }
  }

  useEffect(() => {
    if (!activeRows.length) return;
    refreshQuotes();
    const timer = window.setInterval(refreshQuotes, 1000);
    return () => window.clearInterval(timer);
  }, [activeRows.length]);

  function removeActiveRow(row: TrackedPriorityRow) {
    const closed: PriorityHistoryRow = {
      ...row,
      status: 'removed',
      closed_at: nowIso(),
      close_price: row.last_price ?? row.live_price,
      close_reason: 'Removed manually from Priority Picks page',
    };
    setActiveRows((current) => current.filter((item) => item.key !== row.key));
    if (selectedKey === row.key) setSelectedKey('');
    archiveRows([closed]);
  }

  function addToDashboardMonitor(row: TrackedPriorityRow) {
    const result = addStocksToLiveMonitor([{ ...row, telegram: false }], `${row.horizon}-priority`);
    toast?.push(`${row.symbol} added to dashboard live monitor`, result.added || result.updated ? 'success' : 'warning');
  }

  function clearReport() {
    setHistoryRows([]);
    toast?.push('Priority comparison report cleared', 'success');
  }

  function exportReport() {
    const rows = historyRowsRef.current;
    const columns = ['Symbol', 'Type', 'Suggested Entry Time', 'Outcome', 'Entry', 'Stoploss', 'Target 1', 'Close Price', 'Closed At', 'Reason'];
    const csv = [columns.join(','), ...rows.map((row) => [
      row.symbol,
      row.horizon,
      formatDateTime(row.suggested_entry_time),
      row.status,
      row.entry_price ?? row.entry ?? '',
      row.stop_loss ?? row.stoploss ?? '',
      row.target1 ?? row.target_1 ?? '',
      row.close_price ?? '',
      formatDateTime(row.closed_at),
      `"${String(row.close_reason || '').replace(/"/g, '""')}"`,
    ].join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `priority_picks_report_${Date.now()}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  const filteredActive = useMemo(() => {
    const text = query.toLowerCase();
    return activeRows.filter((row) => `${row.symbol} ${row.horizon} ${row.source_name || ''} ${row.action || ''}`.toLowerCase().includes(text));
  }, [activeRows, query]);
  const intradayActive = filteredActive.filter((row) => row.horizon === 'intraday');
  const swingActive = filteredActive.filter((row) => row.horizon === 'swing');

  const totalSuggested = activeRows.length + historyRows.length;
  const targetHits = historyRows.filter((row) => row.status === 'target_hit').length;
  const stoplossHits = historyRows.filter((row) => row.status === 'stoploss_hit').length;
  const removed = historyRows.filter((row) => row.status === 'removed').length;
  const closedTrades = targetHits + stoplossHits;
  const successRate = closedTrades ? `${Math.round((targetHits / closedTrades) * 100)}%` : 'Waiting';
  const recentMoves = historyRows.slice(0, 5);

  function renderPriorityRows(rows: TrackedPriorityRow[], title: string, emptyBody: string) {
    return (
      <TerminalPanel eyebrow={title.includes('Intraday') ? 'Intraday Priority' : 'Swing Priority'} title={title} actions={<Toolbar search={query} setSearch={setQuery} />}>
        <div className="priority-grid">
          <div className="priority-grid-head">
            <span>Symbol</span>
            <span>LTP</span>
            <span>Entry</span>
            <span>SL</span>
            <span>Targets</span>
            <span>Profit</span>
            <span>Suggested Entry</span>
            <span>Status</span>
            <span>Actions</span>
          </div>
          {!rows.length && <div className="empty-inline">{loading ? 'Refreshing scan sources...' : emptyBody}</div>}
          {rows.map((row) => {
            const selected = selectedKey === row.key;
            return (
              <React.Fragment key={row.key}>
                <button className={`priority-grid-row ${selected ? 'is-selected' : ''}`} type="button" onClick={() => setSelectedKey(selected ? '' : row.key)}>
                  <span><strong>{row.symbol}</strong><small>{row.source_name || row.priority_source || '-'}</small></span>
                  <span>INR {formatPrice(row.last_price ?? row.live_price ?? row.current_price)}</span>
                  <span>INR {formatPrice(row.entry_price ?? row.entry)}</span>
                  <span>INR {formatPrice(row.stop_loss ?? row.stoploss)}</span>
                  <span>INR {formatPrice(row.target1 ?? row.target_1)} / {formatPrice(row.target2 ?? row.target_2)}</span>
                  <span className="status-good">{formatPct(row.priority_profit_pct)}<small>RR {row.risk_reward || row.rrr || '-'}</small></span>
                  <span>{formatDateTime(row.suggested_entry_time)}</span>
                  <span>{row.last_checked ? `Checked ${formatDateTime(row.last_checked)}` : 'Waiting quote'}</span>
                  <span className="priority-row-actions" onClick={(event) => event.stopPropagation()}>
                    <button className="icon-button" type="button" title="Add to dashboard live monitor" onClick={() => addToDashboardMonitor(row)}><BellPlus size={15} /></button>
                    <button className="icon-button" type="button" title="Delete from priority picks" onClick={() => removeActiveRow(row)}><Trash2 size={15} /></button>
                  </span>
                </button>
                {selected && (
                  <div className="selected-stock-detail selected-stock-detail--inline priority-selected-detail">
                    <div>
                      <span>Selected Stock</span>
                      <strong>{row.symbol}</strong>
                      <small>{row.horizon} / {row.source_name || row.priority_source || 'scanner'}</small>
                    </div>
                    <p>{reasonText(row)}</p>
                    <div className="selected-stock-actions">
                      <button className="btn-secondary" type="button" onClick={() => addToDashboardMonitor(row)}><BellPlus size={15} /> Dashboard Monitor</button>
                      <button className="btn-secondary" type="button" onClick={() => removeActiveRow(row)}><Trash2 size={15} /> Delete</button>
                      <span className="status-badge status-good">Suggested {formatDateTime(row.suggested_entry_time)}</span>
                      <span className="status-badge status-warn">Found {formatDateTime(row.found_at)}</span>
                      <button className="icon-button" type="button" title="Close details" onClick={() => setSelectedKey('')}><X size={15} /></button>
                    </div>
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      </TerminalPanel>
    );
  }

  return (
    <main>
      <PageHero
        eyebrow="Priority Picks"
        title="High-Profit Priority Control Center"
        description="Continuously tracks top intraday and swing candidates from Groww, custom scans, scanner outputs, and backend reports, then archives target and stoploss outcomes for comparison."
        actions={<>
          <button className="btn-primary" type="button" onClick={loadPrioritySources}><PlayCircle size={16} /> Refresh Sources</button>
          <button className="btn-secondary" type="button" onClick={exportReport} disabled={!historyRows.length}><Download size={16} /> Export Report</button>
        </>}
        metrics={[
          { label: 'Active Picks', value: String(activeRows.length), tone: activeRows.length ? 'good' : 'warn' },
          { label: 'Suggested Total', value: String(totalSuggested), tone: totalSuggested ? 'good' : 'info' },
          { label: 'Target Hits', value: String(targetHits), tone: targetHits ? 'good' : 'info' },
          { label: 'Success Rate', value: successRate, tone: targetHits ? 'good' : 'warn' },
        ]}
      />

      <div className="metric-grid">
        <MetricTile label="Intraday Active" value={activeRows.filter((row) => row.horizon === 'intraday').length} detail="from Groww, custom intraday, premarket, open-confirmation, scanner rows" icon={Target} tone="good" />
        <MetricTile label="Swing Active" value={activeRows.filter((row) => row.horizon === 'swing').length} detail="from swing and custom swing scan rows" icon={Trophy} tone="info" />
        <MetricTile label="Failed / Stoploss" value={stoplossHits} detail="moved to comparison report automatically" icon={Trash2} tone={stoplossHits ? 'bad' : 'good'} />
        <MetricTile label="Manual Removed" value={removed} detail="kept in report with removal reason" icon={Trash2} tone={removed ? 'warn' : 'info'} />
      </div>

      <TerminalPanel eyebrow="Automation" title="Continuous Priority Rules" description={sourceMessage}>
        <div className="form-grid">
          <label className="field field--inline">
            <span>Telegram alerts</span>
            <input type="checkbox" checked={settings.telegramEnabled} onChange={(event) => updateSettings({ telegramEnabled: event.target.checked })} />
          </label>
          <label className="field field--inline">
            <span>Alert when found</span>
            <input type="checkbox" checked={settings.alertFound} onChange={(event) => updateSettings({ alertFound: event.target.checked })} />
          </label>
          <label className="field field--inline">
            <span>Alert target hit</span>
            <input type="checkbox" checked={settings.alertTarget} onChange={(event) => updateSettings({ alertTarget: event.target.checked })} />
          </label>
          <label className="field field--inline">
            <span>Alert stoploss hit</span>
            <input type="checkbox" checked={settings.alertStoploss} onChange={(event) => updateSettings({ alertStoploss: event.target.checked })} />
          </label>
          <label className="field">
            <span>Minimum Profit %</span>
            <select value={settings.minProfitPct} onChange={(event) => updateSettings({ minProfitPct: Number(event.target.value) })}>
              <option value={3}>3%+</option>
              <option value={4}>4%+</option>
              <option value={5}>5%+</option>
            </select>
          </label>
          <label className="field">
            <span>Priority Limit</span>
            <select value={settings.limit} onChange={(event) => updateSettings({ limit: Number(event.target.value) })}>
              <option value={3}>Top 3</option>
              <option value={5}>Top 5</option>
            </select>
          </label>
        </div>
        <p className="small"><Bell size={14} /> Telegram is disabled by default. Alerts are sent only when a new stock is added, target is hit, or stoploss is hit.</p>
      </TerminalPanel>

      <TerminalPanel eyebrow="Movement" title="Priority Movement Summary">
        <div className="priority-movement-grid">
          <div><span>Stocks Suggested</span><strong>{totalSuggested}</strong><small>active + report history</small></div>
          <div><span>Hit Target</span><strong className="status-good">{targetHits}</strong><small>auto-moved to report</small></div>
          <div><span>Hit Stoploss</span><strong className="status-bad">{stoplossHits}</strong><small>auto-moved to report</small></div>
          <div><span>Manual Deletes</span><strong>{removed}</strong><small>archived without Telegram alert</small></div>
        </div>
        {recentMoves.length > 0 && (
          <div className="priority-recent-moves">
            {recentMoves.map((row) => (
              <span key={`${row.key}-${row.closed_at}`} className={`status-badge ${row.status === 'target_hit' ? 'status-good' : row.status === 'stoploss_hit' ? 'status-bad' : 'status-warn'}`}>
                {row.symbol}: {row.status.replace(/_/g, ' ')}
              </span>
            ))}
          </div>
        )}
      </TerminalPanel>

      {renderPriorityRows(intradayActive, 'High Profit Intraday Priority Picks', 'No intraday priority picks currently meet the complete trade-plan and profit rules.')}
      {renderPriorityRows(swingActive, 'High Profit Swing Priority Picks', 'No swing priority picks currently meet the complete trade-plan and profit rules.')}

      <TerminalPanel eyebrow="Comparison Report" title="Suggested vs Target / Stoploss Outcomes" actions={<button className="btn-secondary" type="button" onClick={clearReport} disabled={!historyRows.length}><Trash2 size={15} /> Clear Report</button>}>
        <DataTable
          columns={['Symbol', 'Type', 'Suggested Entry Time', 'Outcome', 'Entry', 'Close', 'Closed At', 'Reason']}
          rows={historyRows.map((row) => [
            <strong key={`${row.key}-history-symbol`}>{row.symbol}</strong>,
            row.horizon,
            formatDateTime(row.suggested_entry_time),
            <span key={`${row.key}-history-status`} className={`status-badge ${row.status === 'target_hit' ? 'status-good' : row.status === 'stoploss_hit' ? 'status-bad' : 'status-warn'}`}>{row.status.replace(/_/g, ' ')}</span>,
            `INR ${formatPrice(row.entry_price ?? row.entry)}`,
            `INR ${formatPrice(row.close_price)}`,
            formatDateTime(row.closed_at),
            row.close_reason,
          ])}
          emptyTitle="No completed priority records"
          emptyBody="When a priority stock hits target, stoploss, or is removed, it will be archived here for comparison."
        />
      </TerminalPanel>
    </main>
  );
}
