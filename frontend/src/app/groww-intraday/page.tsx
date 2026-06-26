"use client";
import React, { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Activity, Clock, ExternalLink, Play, RefreshCw, Send, Settings2, UploadCloud, Plus, Trash2, Check } from 'lucide-react';
import StockGrid from '@/components/molecules/LazyStockGrid';
import { getGrowwIntradayStocks, getV20Quote, getV20Quotes, getWatchlist, addWatchlistItem, deleteWatchlistItem } from '@/lib/api';
import { useToast } from '@/components/layout/ToastProvider';
import { DataTable, MetricTile, PageHero, TerminalPanel } from '@/components/terminal/TerminalPrimitives';
import { defaultGrowwSettings, GROWW_EVENT, GROWW_PRIORITY_UPDATED_EVENT, GrowwAutoSettings, pushSymbolsToIntraday, readGrowwPriorityActive, readGrowwPriorityHistory, readGrowwResults, readGrowwSettings, runGrowwIntradayAnalysis, writeGrowwPriorityActive, writeGrowwPriorityHistory, writeGrowwSettings } from '@/lib/growwIntraday';
import GrowwPriorityPanel from '@/components/organisms/GrowwPriorityPanel';

type GrowwRow = { 
  company: string; 
  symbol: string; 
  resolved: boolean; 
  candidates?: string[]; 
  source?: string;
  current_price?: number;
  price_change_pct?: number;
  open?: number;
  high?: number;
  low?: number;
  previous_close?: number;
  vwap?: number;
  ema9?: number;
  ema20?: number;
  ema50?: number;
  ema200?: number;
  volume_spike?: number;
  breakout_level?: number;
  support?: number;
  resistance?: number;
  target1?: number;
  target2?: number;
  stop_loss?: number;
  expected_profit_percent?: number;
  expected_loss_percent?: number;
  risk_reward_ratio?: number;
  quality_score?: number;
  quality_label?: string;
  decision?: string;
  action?: string;
  reason?: string;
  is_newly_added?: boolean;
  is_custom_watchlist?: boolean;
  suggested_at?: string;
  pl_after_suggestion?: number;
  already_moved_percent?: number;
  remaining_upside_percent?: number;
  distance_to_breakout_percent?: number;
  distance_from_vwap_percent?: number;
  distance_from_intraday_high_percent?: number;
  intraday_high?: number;
  overall_score?: number;
};

export default function GrowwIntradayPage() {
  const toast = useToast();
  const [rows, setRows] = useState<GrowwRow[]>([]);
  const [resultRows, setResultRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scanId, setScanId] = useState('');
  const [message, setMessage] = useState('Fetch Groww intraday list to start.');
  const [settings, setSettings] = useState<GrowwAutoSettings>(defaultGrowwSettings);
  const [activePriorityRows, setActivePriorityRows] = useState<any[]>([]);
  const [historyPriorityRows, setHistoryPriorityRows] = useState<any[]>([]);
  const [showAutoConfig, setShowAutoConfig] = useState(false);
  const [displayLimit, setDisplayLimit] = useState(10);

  // Advanced Quantitative Filters state
  const [filterMinPrice, setFilterMinPrice] = useState<string>('');
  const [filterMaxPrice, setFilterMaxPrice] = useState<string>('');
  const [filterMinChange, setFilterMinChange] = useState<string>('');
  const [filterMaxChange, setFilterMaxChange] = useState<string>('');
  const [filterMinVolume, setFilterMinVolume] = useState<string>('');
  const [filterMaxBreakoutDist, setFilterMaxBreakoutDist] = useState<string>('');
  const [filterMaxVwapDist, setFilterMaxVwapDist] = useState<string>('');
  const [filterMinRR, setFilterMinRR] = useState<string>('');
  const [filterMinProfit, setFilterMinProfit] = useState<string>('');
  const [filterMaxAlreadyMoved, setFilterMaxAlreadyMoved] = useState<string>('');
  const [filterMinRemainingUpside, setFilterMinRemainingUpside] = useState<string>('');
  
  const [filterNearHigh, setFilterNearHigh] = useState<boolean>(false);
  const [filterBuyReadyOnly, setFilterBuyReadyOnly] = useState<boolean>(false);
  const [filterWaitOnly, setFilterWaitOnly] = useState<boolean>(false);
  const [filterAvoidOnly, setFilterAvoidOnly] = useState<boolean>(false);
  const [filterNewlyAdded, setFilterNewlyAdded] = useState<boolean>(false);
  const [filterHighQualityScore, setFilterHighQualityScore] = useState<boolean>(false);
  const [filterCustomWatchlist, setFilterCustomWatchlist] = useState<boolean>(false);

  const [watchlistSymbols, setWatchlistSymbols] = useState<Set<string>>(new Set());

  async function refreshWatchlist() {
    try {
      const data = await getWatchlist();
      if (data?.items) {
        setWatchlistSymbols(new Set(data.items.map(item => item.symbol.toUpperCase())));
      }
    } catch (err) {
      console.error("Failed to load watchlist:", err);
    }
  }

  useEffect(() => {
    refreshWatchlist();
  }, []);

  const symbols = useMemo(() => Array.from(new Set(rows.filter((row) => row.symbol).map((row) => row.symbol))), [rows]);
  const filteredResultRows = useMemo(() => {
    return resultRows.filter((row) => row.action && row.action !== 'AVOID');
  }, [resultRows]);

  const filteredRows = useMemo(() => {
    return rows.filter((row) => {
      if (!row.symbol) return false;
      
      // Price range
      if (filterMinPrice) {
        const val = Number(row.current_price);
        if (isNaN(val) || val < Number(filterMinPrice)) return false;
      }
      if (filterMaxPrice) {
        const val = Number(row.current_price);
        if (isNaN(val) || val > Number(filterMaxPrice)) return false;
      }
      
      // Change %
      if (filterMinChange) {
        const val = Number(row.price_change_pct);
        if (isNaN(val) || val < Number(filterMinChange)) return false;
      }
      if (filterMaxChange) {
        const val = Number(row.price_change_pct);
        if (isNaN(val) || val > Number(filterMaxChange)) return false;
      }
      
      // Volume vs average
      if (filterMinVolume) {
        const val = Number(row.volume_spike);
        if (isNaN(val) || val < Number(filterMinVolume)) return false;
      }
      
      // Breakout distance
      if (filterMaxBreakoutDist) {
        const val = Number(row.distance_to_breakout_percent);
        if (isNaN(val) || val > Number(filterMaxBreakoutDist)) return false;
      }
      
      // VWAP distance
      if (filterMaxVwapDist) {
        const val = Number(row.distance_from_vwap_percent);
        if (isNaN(val) || val > Number(filterMaxVwapDist)) return false;
      }
      
      // Risk reward
      if (filterMinRR) {
        const val = Number(row.risk_reward_ratio);
        if (isNaN(val) || val < Number(filterMinRR)) return false;
      }
      
      // Expected profit %
      if (filterMinProfit) {
        const val = Number(row.expected_profit_percent);
        if (isNaN(val) || val < Number(filterMinProfit)) return false;
      }
      
      // Already moved %
      if (filterMaxAlreadyMoved) {
        const val = Number(row.already_moved_percent);
        if (isNaN(val) || val > Number(filterMaxAlreadyMoved)) return false;
      }
      
      // Remaining upside %
      if (filterMinRemainingUpside) {
        const val = Number(row.remaining_upside_percent);
        if (isNaN(val) || val < Number(filterMinRemainingUpside)) return false;
      }
      
      // Near high
      if (filterNearHigh) {
        const val = Number(row.distance_from_intraday_high_percent);
        if (isNaN(val) || val >= 0.4) return false;
      }
      
      // Decision filters
      if (filterBuyReadyOnly && row.decision !== 'BUY READY') {
        return false;
      }
      if (filterWaitOnly && !row.decision?.startsWith('WAIT')) {
        return false;
      }
      if (filterAvoidOnly && !row.decision?.startsWith('AVOID') && row.decision !== 'AVOID') {
        return false;
      }
      
      // Newly added
      if (filterNewlyAdded && !row.is_newly_added) {
        return false;
      }
      
      // High quality score
      if (filterHighQualityScore && Number(row.quality_score ?? 0) < 75) {
        return false;
      }
      
      // Custom watchlist added
      if (filterCustomWatchlist && !row.is_custom_watchlist) {
        return false;
      }
      
      return true;
    });
  }, [
    rows,
    filterMinPrice,
    filterMaxPrice,
    filterMinChange,
    filterMaxChange,
    filterMinVolume,
    filterMaxBreakoutDist,
    filterMaxVwapDist,
    filterMinRR,
    filterMinProfit,
    filterMaxAlreadyMoved,
    filterMinRemainingUpside,
    filterNearHigh,
    filterBuyReadyOnly,
    filterWaitOnly,
    filterAvoidOnly,
    filterNewlyAdded,
    filterHighQualityScore,
    filterCustomWatchlist
  ]);

  const unresolved = rows.filter((row) => !row.resolved);

  const activeRowsRef = React.useRef<any[]>([]);
  const historyRowsRef = React.useRef<any[]>([]);
  const quoteRefreshingRef = React.useRef(false);

  useEffect(() => {
    activeRowsRef.current = activePriorityRows;
  }, [activePriorityRows]);

  useEffect(() => {
    historyRowsRef.current = historyPriorityRows;
  }, [historyPriorityRows]);

  // 1-second auto-refresh polling effect
  useEffect(() => {
    if (!rows.length || loading) return;
    
    let active = true;
    const interval = setInterval(async () => {
      if (!active) return;
      try {
        const payload = await getGrowwIntradayStocks(settings.limit);
        if (active && payload?.rows) {
          setRows(payload.rows);
        }
      } catch (err) {
        console.error("Failed to auto-refresh Groww Intraday list:", err);
      }
    }, 1000);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [rows.length, loading, settings.limit]);

  useEffect(() => {
    function sync() {
      const nextSettings = readGrowwSettings();
      const latest = readGrowwResults();
      setSettings(nextSettings);
      if (latest.rows.length) {
        setResultRows(latest.rows);
        setScanId(latest.scanId);
        setMessage(latest.message || `Latest Groww auto scan has ${latest.rows.length} filtered stocks.`);
      }
    }
    sync();
    window.addEventListener(GROWW_EVENT, sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener(GROWW_EVENT, sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  useEffect(() => {
    function syncPriority() {
      setActivePriorityRows(readGrowwPriorityActive());
      setHistoryPriorityRows(readGrowwPriorityHistory());
    }
    syncPriority();
    window.addEventListener(GROWW_PRIORITY_UPDATED_EVENT, syncPriority);
    window.addEventListener('storage', syncPriority);
    return () => {
      window.removeEventListener(GROWW_PRIORITY_UPDATED_EVENT, syncPriority);
      window.removeEventListener('storage', syncPriority);
    };
  }, []);

  function targetForOutcome(row: any) {
    return Number(row.target1 || row.target_1 || row.target2 || row.target_2 || 0);
  }

  function stopForOutcome(row: any) {
    return Number(row.stop_loss || row.stoploss || 0);
  }

  function isSellSetup(row: any) {
    return /sell|short/i.test(`${row.action || ''} ${row.signal || ''} ${row.trade_type || ''}`);
  }

  function outcomeForPrice(row: any, livePrice: number) {
    const target = targetForOutcome(row);
    const stop = stopForOutcome(row);
    if (!livePrice || (!target && !stop)) return null;
    if (isSellSetup(row)) {
      if (stop && livePrice >= stop) return { status: 'stoploss_hit' as const, reason: `Sell setup stoploss hit at INR ${livePrice.toFixed(2)}` };
      if (target && livePrice <= target) return { status: 'target_hit' as const, reason: `Sell setup target hit at INR ${livePrice.toFixed(2)}` };
      return null;
    }
    if (stop && livePrice <= stop) return { status: 'stoploss_hit' as const, reason: `Stoploss hit at INR ${livePrice.toFixed(2)}` };
    if (target && livePrice >= target) return { status: 'target_hit' as const, reason: `Target hit at INR ${livePrice.toFixed(2)}` };
    return null;
  }

  useEffect(() => {
    if (!activePriorityRows.length) return;
    
    async function refreshQuotes() {
      const rows = activeRowsRef.current;
      if (!rows.length || quoteRefreshingRef.current) return;
      quoteRefreshingRef.current = true;
      try {
        const symbols = rows.map((r) => r.symbol).filter(Boolean);
        const payload = await getV20Quotes(symbols);
        const quotes = payload?.quotes || {};
        
        const closedRows: any[] = [];
        const nextActive: any[] = [];

        rows.forEach((row) => {
          const quote = quotes[row.symbol];
          if (!quote) {
            nextActive.push(row);
            return;
          }
          const live = Number(quote.current_price ?? quote.regularMarketPrice ?? quote.price ?? quote.last_close ?? row.live_price ?? row.last_price ?? 0);
          if (!Number.isFinite(live) || live <= 0) {
            nextActive.push(row);
            return;
          }

          const enriched = {
            ...row,
            last_price: Math.round(live * 100) / 100,
            live_price: Math.round(live * 100) / 100,
            last_checked: new Date().toISOString()
          };
          const outcome = outcomeForPrice(enriched, live);
          if (outcome) {
            closedRows.push({
              ...enriched,
              status: outcome.status,
              closed_at: new Date().toISOString(),
              close_price: Math.round(live * 100) / 100,
              close_reason: outcome.reason,
            });
          } else {
            nextActive.push(enriched);
          }
        });

        if (closedRows.length) {
          const nextHistory = [...closedRows, ...historyRowsRef.current].slice(0, 500);
          writeGrowwPriorityHistory(nextHistory);
          setHistoryPriorityRows(nextHistory);
          
          closedRows.forEach((closedRow) => {
            toast.push(`Groww Priority: ${closedRow.symbol} moved to history (${closedRow.status === 'target_hit' ? 'Target hit' : 'Stoploss hit'})`, 'success');
          });
        }
        
        writeGrowwPriorityActive(nextActive);
        setActivePriorityRows(nextActive);
      } catch (err) {
        console.error("Groww priority quote batch refresh failed:", err);
      } finally {
        quoteRefreshingRef.current = false;
      }
    }

    refreshQuotes();
    const timer = window.setInterval(refreshQuotes, 1000);
    return () => window.clearInterval(timer);
  }, [activePriorityRows.length]);

  function clearAuditHistory() {
    writeGrowwPriorityHistory([]);
    setHistoryPriorityRows([]);
    toast.push('Groww priority outcome audit logs cleared', 'success');
  }

  function updateSettings(patch: Partial<GrowwAutoSettings>) {
    const next = { ...settings, ...patch };
    setSettings(next);
    writeGrowwSettings(next);
  }

  async function fetchGroww() {
    setLoading(true);
    setMessage('Fetching Groww intraday page...');
    try {
      const payload = await getGrowwIntradayStocks(settings.limit);
      setRows(payload.rows || []);
      setMessage(`${payload.resolved_count || 0} symbols resolved from ${payload.count || 0} Groww rows.`);
      toast.push('Groww intraday list loaded', 'success');
    } catch (error: any) {
      setMessage(error?.message || 'Unable to fetch Groww intraday list');
      toast.push('Unable to fetch Groww intraday list', 'error');
    } finally {
      setLoading(false);
    }
  }

  async function runGrowwScan() {
    setScanning(true);
    setMessage('Routing Groww symbols through IntradayScannerService quick cache...');
    try {
      const saved = await runGrowwIntradayAnalysis(settings.limit);
      setScanId(saved.scanId);
      setResultRows(saved.rows);
      setMessage(`Quick analysis complete. ${saved.analyzedCount || 0} new/stale symbols analyzed, ${saved.cachedCount || 0} reused from cache, ${saved.rows.length} opportunities kept.`);
      toast.push(`${saved.rows.length} Groww intraday opportunities synced`, 'success');
    } catch (error: any) {
      setMessage(error?.message || 'Groww intraday scan failed');
      toast.push(error?.message || 'Groww intraday scan failed', 'error');
    } finally {
      setScanning(false);
    }
  }

  function pushWithoutScan() {
    if (!symbols.length) {
      toast.push('No resolved Groww symbols to push', 'warning');
      return;
    }
    pushSymbolsToIntraday(symbols);
    toast.push(`${symbols.length} Groww symbols pushed to intraday scanner input`, 'success');
  }

  return (
    <main>
      <PageHero
        eyebrow="Third Party Source"
        title="Groww Intraday Import"
        description="Use Groww only as a symbol source, then route symbols through the shared IntradayScannerService quick engine with cache-first analysis."
        actions={<>
          <a className="btn-secondary" href="https://groww.in/stocks/intraday" target="_blank" rel="noreferrer"><ExternalLink size={16} /> Open Groww</a>
          <button className="btn-secondary" type="button" onClick={fetchGroww} disabled={loading}><RefreshCw size={16} /> {loading ? 'Fetching' : 'Fetch List'}</button>
          <button className="btn-secondary" type="button" onClick={() => setShowAutoConfig(!showAutoConfig)}><Settings2 size={16} /> {showAutoConfig ? 'Hide Config' : 'Auto Config'}</button>
          <button className="btn-primary" type="button" onClick={runGrowwScan} disabled={scanning || loading}><Play size={16} /> {scanning ? 'Analyzing' : 'Analyze Intraday'}</button>
        </>}
        metrics={[
          { label: 'Resolved Symbols', value: String(symbols.length), tone: symbols.length ? 'good' : 'warn' },
          { label: 'Unresolved Names', value: String(unresolved.length), tone: unresolved.length ? 'warn' : 'good' },
          { label: 'Scan ID', value: scanId || 'Not started' },
          { label: 'Auto Check', value: settings.enabled ? `${settings.intervalMinutes} min` : 'Off', tone: settings.enabled ? 'good' : 'warn' },
        ]}
      />

      {showAutoConfig && (
        <div style={{
          background: 'var(--surface-3)',
          border: '1px solid var(--border)',
          borderRadius: '6px',
          padding: '12px',
          margin: '0 16px 14px 16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '8px'
        }}>
          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', 
            gap: '8px' 
          }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '0.65rem', padding: '4px', background: 'rgba(0,0,0,0.15)', border: '1px solid rgba(255,255,255,0.03)', borderRadius: '4px' }}>
              <span style={{ color: 'var(--muted)', fontWeight: 700 }}>Enable auto checking</span>
              <input type="checkbox" checked={settings.enabled} onChange={(event) => updateSettings({ enabled: event.target.checked })} style={{ marginTop: '4px', width: '16px', height: '16px', cursor: 'pointer' }} />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '0.65rem', padding: '4px', background: 'rgba(0,0,0,0.15)', border: '1px solid rgba(255,255,255,0.03)', borderRadius: '4px' }}>
              <span style={{ color: 'var(--muted)', fontWeight: 700 }}>Interval Minutes</span>
              <input type="number" min={1} max={240} value={settings.intervalMinutes} onChange={(event) => updateSettings({ intervalMinutes: Number(event.target.value) || 15 })} style={{ padding: '2px 4px', fontSize: '0.74rem', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '3px' }} />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '0.65rem', padding: '4px', background: 'rgba(0,0,0,0.15)', border: '1px solid rgba(255,255,255,0.03)', borderRadius: '4px' }}>
              <span style={{ color: 'var(--muted)', fontWeight: 700 }}>Groww Row Limit</span>
              <input type="number" min={5} max={200} value={settings.limit} onChange={(event) => updateSettings({ limit: Number(event.target.value) || 80 })} style={{ padding: '2px 4px', fontSize: '0.74rem', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '3px' }} />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '0.65rem', padding: '4px', background: 'rgba(0,0,0,0.15)', border: '1px solid rgba(255,255,255,0.03)', borderRadius: '4px' }}>
              <span style={{ color: 'var(--muted)', fontWeight: 700 }}>Priority Picks</span>
              <select value={settings.priorityLimit || 5} onChange={(event) => updateSettings({ priorityLimit: Number(event.target.value) })} style={{ padding: '2px 4px', fontSize: '0.74rem', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '3px' }}>
                <option value={3}>Top 3</option>
                <option value={5}>Top 5</option>
              </select>
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '0.65rem', padding: '4px', background: 'rgba(0,0,0,0.15)', border: '1px solid rgba(255,255,255,0.03)', borderRadius: '4px' }}>
              <span style={{ color: 'var(--muted)', fontWeight: 700 }}>Minimum Profit %</span>
              <select value={settings.priorityMinProfitPct || 3} onChange={(event) => updateSettings({ priorityMinProfitPct: Number(event.target.value) })} style={{ padding: '2px 4px', fontSize: '0.74rem', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '3px' }}>
                <option value={3}>3%+</option>
                <option value={4}>4%+</option>
                <option value={5}>5%+</option>
              </select>
            </label>
          </div>
          <div style={{ fontSize: '0.65rem', color: 'var(--muted)', marginTop: '4px' }}>
            When enabled, the app keeps checking Groww and refreshes the Groww results cache only. Intraday scanner input changes only when you explicitly send or pull the list.
          </div>
        </div>
      )}

      <div className="metric-grid">
        <MetricTile label="Source Status" value={loading ? 'Fetching' : rows.length ? 'Loaded' : 'Waiting'} detail={message} icon={UploadCloud} tone={rows.length ? 'good' : 'warn'} />
        <MetricTile label="Analysis Status" value={scanning ? 'Running' : resultRows.length ? 'Complete' : 'Idle'} detail="IntradayScannerService quick engine" icon={Activity} tone={resultRows.length ? 'good' : scanning ? 'warn' : 'info'} />
        <MetricTile label="Auto Scheduler" value={settings.enabled ? 'Enabled' : 'Disabled'} detail={`checks every ${settings.intervalMinutes} minute(s)`} icon={Clock} tone={settings.enabled ? 'good' : 'warn'} />
      </div>

      <GrowwPriorityPanel
        eyebrow="Groww Priority"
        title="High Profit Groww Priority Picks"
        rows={activePriorityRows}
        updatedAt={readGrowwResults().updatedAt}
        emptyText="No Groww intraday stocks currently meet the profit threshold with complete entry, stoploss, and target levels."
      />

      <TerminalPanel 
        eyebrow="Groww Priority Audit" 
        title="Groww Priority Outcomes & Comparison"
        actions={
          <button 
            className="btn-secondary" 
            type="button" 
            onClick={clearAuditHistory} 
            disabled={!historyPriorityRows.length}
          >
            Clear Audit
          </button>
        }
      >
        <DataTable
          columns={['Symbol', 'Outcome', 'Entry Price', 'Close Price', 'Target', 'Stop Loss', 'Closed At', 'Reason']}
          rows={historyPriorityRows.map((row, index) => [
            <strong key={`${row.symbol}-${index}`}>{row.symbol}</strong>,
            <span key={`${row.symbol}-status-${index}`} className={`status-badge ${row.status === 'target_hit' ? 'status-good' : 'status-bad'}`}>
              {row.status === 'target_hit' ? 'TARGET HIT' : 'STOPLOSS HIT'}
            </span>,
            row.entry_price ? `INR ${row.entry_price.toFixed(2)}` : '-',
            row.close_price ? `INR ${row.close_price.toFixed(2)}` : '-',
            row.target1 ? `INR ${row.target1.toFixed(2)}` : '-',
            row.stop_loss ? `INR ${row.stop_loss.toFixed(2)}` : '-',
            row.closed_at ? new Date(row.closed_at).toLocaleString('en-IN') : '-',
            row.close_reason || '-',
          ])}
          emptyTitle="No completed Groww priority records"
          emptyBody="When a Groww priority stock hits target or stoploss, it will be automatically archived here for comparison and auditing."
        />
      </TerminalPanel>

      {/* Advanced Quantitative Filters Panel */}
      <div style={{
        background: 'var(--surface-2)',
        border: '1px solid var(--border)',
        borderRadius: '8px',
        padding: '16px',
        margin: '0 16px 20px 16px',
        boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0, fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text)' }}>
            Advanced Quantitative Filters ({filteredRows.length} of {rows.length} matched)
          </h3>
          <button className="btn-secondary" style={{ padding: '4px 8px', fontSize: '0.7rem' }} onClick={() => {
            setFilterMinPrice('');
            setFilterMaxPrice('');
            setFilterMinChange('');
            setFilterMaxChange('');
            setFilterMinVolume('');
            setFilterMaxBreakoutDist('');
            setFilterMaxVwapDist('');
            setFilterMinRR('');
            setFilterMinProfit('');
            setFilterMaxAlreadyMoved('');
            setFilterMinRemainingUpside('');
            setFilterNearHigh(false);
            setFilterBuyReadyOnly(false);
            setFilterWaitOnly(false);
            setFilterAvoidOnly(false);
            setFilterNewlyAdded(false);
            setFilterHighQualityScore(false);
            setFilterCustomWatchlist(false);
          }}>Reset Filters</button>
        </div>

        {/* Input fields grid */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: '12px'
        }}>
          {/* Price Range */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '0.65rem', color: 'var(--muted)', fontWeight: 700 }}>Price Range (INR)</span>
            <div style={{ display: 'flex', gap: '4px' }}>
              <input type="number" placeholder="Min" value={filterMinPrice} onChange={(e) => setFilterMinPrice(e.target.value)} style={{ width: '50%', padding: '4px 8px', fontSize: '0.75rem', background: 'var(--surface-3)', border: '1px solid var(--border)', borderRadius: '4px', color: 'var(--text)' }} />
              <input type="number" placeholder="Max" value={filterMaxPrice} onChange={(e) => setFilterMaxPrice(e.target.value)} style={{ width: '50%', padding: '4px 8px', fontSize: '0.75rem', background: 'var(--surface-3)', border: '1px solid var(--border)', borderRadius: '4px', color: 'var(--text)' }} />
            </div>
          </div>

          {/* Change % Range */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '0.65rem', color: 'var(--muted)', fontWeight: 700 }}>Change % Range</span>
            <div style={{ display: 'flex', gap: '4px' }}>
              <input type="number" step="0.1" placeholder="Min" value={filterMinChange} onChange={(e) => setFilterMinChange(e.target.value)} style={{ width: '50%', padding: '4px 8px', fontSize: '0.75rem', background: 'var(--surface-3)', border: '1px solid var(--border)', borderRadius: '4px', color: 'var(--text)' }} />
              <input type="number" step="0.1" placeholder="Max" value={filterMaxChange} onChange={(e) => setFilterMaxChange(e.target.value)} style={{ width: '50%', padding: '4px 8px', fontSize: '0.75rem', background: 'var(--surface-3)', border: '1px solid var(--border)', borderRadius: '4px', color: 'var(--text)' }} />
            </div>
          </div>

          {/* Volume vs Avg */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '0.65rem', color: 'var(--muted)', fontWeight: 700 }}>Min Volume vs Average</span>
            <input type="number" step="0.1" placeholder="Min volume spike" value={filterMinVolume} onChange={(e) => setFilterMinVolume(e.target.value)} style={{ padding: '4px 8px', fontSize: '0.75rem', background: 'var(--surface-3)', border: '1px solid var(--border)', borderRadius: '4px', color: 'var(--text)' }} />
          </div>

          {/* Breakout Distance */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '0.65rem', color: 'var(--muted)', fontWeight: 700 }}>Max Breakout Distance %</span>
            <input type="number" step="0.05" placeholder="Max distance %" value={filterMaxBreakoutDist} onChange={(e) => setFilterMaxBreakoutDist(e.target.value)} style={{ padding: '4px 8px', fontSize: '0.75rem', background: 'var(--surface-3)', border: '1px solid var(--border)', borderRadius: '4px', color: 'var(--text)' }} />
          </div>

          {/* VWAP Distance */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '0.65rem', color: 'var(--muted)', fontWeight: 700 }}>Max VWAP Distance %</span>
            <input type="number" step="0.1" placeholder="Max distance %" value={filterMaxVwapDist} onChange={(e) => setFilterMaxVwapDist(e.target.value)} style={{ padding: '4px 8px', fontSize: '0.75rem', background: 'var(--surface-3)', border: '1px solid var(--border)', borderRadius: '4px', color: 'var(--text)' }} />
          </div>

          {/* Risk Reward */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '0.65rem', color: 'var(--muted)', fontWeight: 700 }}>Min Risk Reward Ratio</span>
            <input type="number" step="0.1" placeholder="Min RR ratio" value={filterMinRR} onChange={(e) => setFilterMinRR(e.target.value)} style={{ padding: '4px 8px', fontSize: '0.75rem', background: 'var(--surface-3)', border: '1px solid var(--border)', borderRadius: '4px', color: 'var(--text)' }} />
          </div>

          {/* Expected Profit % */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '0.65rem', color: 'var(--muted)', fontWeight: 700 }}>Min Expected Profit %</span>
            <input type="number" step="0.1" placeholder="Min profit %" value={filterMinProfit} onChange={(e) => setFilterMinProfit(e.target.value)} style={{ padding: '4px 8px', fontSize: '0.75rem', background: 'var(--surface-3)', border: '1px solid var(--border)', borderRadius: '4px', color: 'var(--text)' }} />
          </div>

          {/* Already Moved % */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '0.65rem', color: 'var(--muted)', fontWeight: 700 }}>Max Already Moved %</span>
            <input type="number" step="0.1" placeholder="Max moved %" value={filterMaxAlreadyMoved} onChange={(e) => setFilterMaxAlreadyMoved(e.target.value)} style={{ padding: '4px 8px', fontSize: '0.75rem', background: 'var(--surface-3)', border: '1px solid var(--border)', borderRadius: '4px', color: 'var(--text)' }} />
          </div>

          {/* Remaining Upside % */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '0.65rem', color: 'var(--muted)', fontWeight: 700 }}>Min Remaining Upside %</span>
            <input type="number" step="0.1" placeholder="Min upside %" value={filterMinRemainingUpside} onChange={(e) => setFilterMinRemainingUpside(e.target.value)} style={{ padding: '4px 8px', fontSize: '0.75rem', background: 'var(--surface-3)', border: '1px solid var(--border)', borderRadius: '4px', color: 'var(--text)' }} />
          </div>
        </div>

        {/* Checkbox filters row */}
        <div style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '16px',
          paddingTop: '8px',
          borderTop: '1px solid var(--border)'
        }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '0.7rem', color: 'var(--text)' }}>
            <input type="checkbox" checked={filterNearHigh} onChange={(e) => setFilterNearHigh(e.target.checked)} />
            Avoid Near High (&lt;0.4%)
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '0.7rem', color: 'var(--text)' }}>
            <input type="checkbox" checked={filterBuyReadyOnly} onChange={(e) => setFilterBuyReadyOnly(e.target.checked)} disabled={filterWaitOnly || filterAvoidOnly} />
            Buy Ready Only
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '0.7rem', color: 'var(--text)' }}>
            <input type="checkbox" checked={filterWaitOnly} onChange={(e) => setFilterWaitOnly(e.target.checked)} disabled={filterBuyReadyOnly || filterAvoidOnly} />
            Wait Only
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '0.7rem', color: 'var(--text)' }}>
            <input type="checkbox" checked={filterAvoidOnly} onChange={(e) => setFilterAvoidOnly(e.target.checked)} disabled={filterBuyReadyOnly || filterWaitOnly} />
            Avoid Only
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '0.7rem', color: 'var(--text)' }}>
            <input type="checkbox" checked={filterNewlyAdded} onChange={(e) => setFilterNewlyAdded(e.target.checked)} />
            Newly Added
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '0.7rem', color: 'var(--text)' }}>
            <input type="checkbox" checked={filterHighQualityScore} onChange={(e) => setFilterHighQualityScore(e.target.checked)} />
            High Quality Score (&ge;75)
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '0.7rem', color: 'var(--text)' }}>
            <input type="checkbox" checked={filterCustomWatchlist} onChange={(e) => setFilterCustomWatchlist(e.target.checked)} />
            Custom Watchlist Added
          </label>
        </div>
      </div>

      <TerminalPanel eyebrow="Groww Source" title="Resolved Intraday Symbols & Advanced Analytics" actions={<>
        <button className="btn-secondary" type="button" onClick={pushWithoutScan}><Send size={15} /> Send to Intraday Input</button>
      </>}>
        <div style={{ overflowX: 'auto', width: '100%' }}>
          <div style={{ minWidth: '2200px' }}>
            <DataTable
              columns={[
                'Symbol / Company', 
                'LTP', 
                'Open/High/Low/Prev Close', 
                'VWAP', 
                'EMA 9/20', 
                'Volume vs Avg', 
                'Breakout', 
                'Support/Resistance', 
                'Target 1/2', 
                'Stop Loss', 
                'Expected Profit %', 
                'Expected Risk %', 
                'Risk Reward', 
                'Score', 
                'Decision', 
                'Reason', 
                'Suggested Time', 
                'P/L after Suggestion',
                'Actions'
              ]}
              rows={filteredRows.map((row) => {
                const isBuy = row.action === 'BUY READY';
                const isWait = row.action === 'WAIT' || row.decision?.startsWith('WAIT');
                const isAvoid = row.action === 'AVOID' || row.decision?.startsWith('AVOID');
                
                let decisionClass = 'status-info';
                if (isBuy) decisionClass = 'status-good';
                if (isWait) decisionClass = 'status-warn';
                if (isAvoid) decisionClass = 'status-bad';
                
                const isAdded = watchlistSymbols.has(row.symbol.toUpperCase());
                
                const handleToggleWatchlist = async () => {
                  try {
                    if (isAdded) {
                      await deleteWatchlistItem(row.symbol);
                      toast.push(`${row.symbol} removed from Watchlist`, 'success');
                    } else {
                      await addWatchlistItem({ symbol: row.symbol, notes: 'groww', monitoring_enabled: true });
                      toast.push(`${row.symbol} added to Watchlist`, 'success');
                    }
                    refreshWatchlist();
                  } catch (err: any) {
                    toast.push(err?.message || "Failed to update watchlist", 'error');
                  }
                };

                return [
                  <div key={`${row.symbol}-info`}>
                    <strong>{row.symbol || '-'}</strong>
                    {row.is_newly_added && <span className="status-badge status-good" style={{ marginLeft: '4px', fontSize: '0.55rem', padding: '1px 3px' }}>NEW</span>}
                    {row.is_custom_watchlist && <span className="status-badge status-info" style={{ marginLeft: '4px', fontSize: '0.55rem', padding: '1px 3px' }}>WATCHLIST</span>}
                    <div style={{ fontSize: '0.62rem', color: 'var(--muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '140px' }}>
                      {row.company || '-'}
                    </div>
                  </div>,
                  
                  <strong key={`${row.symbol}-price`}>
                    {row.current_price ? `INR ${Number(row.current_price).toFixed(2)}` : '-'}
                  </strong>,
                  
                  <div key={`${row.symbol}-ohlc`} style={{ fontSize: '0.68rem', lineHeight: '1.2' }}>
                    <div>O: {row.open ? Number(row.open).toFixed(1) : '-'} | H: {row.high ? Number(row.high).toFixed(1) : '-'}</div>
                    <div>L: {row.low ? Number(row.low).toFixed(1) : '-'} | PC: {row.previous_close ? Number(row.previous_close).toFixed(1) : '-'}</div>
                  </div>,
                  
                  <span key={`${row.symbol}-vwap`}>
                    {row.vwap ? Number(row.vwap).toFixed(2) : '-'}
                  </span>,
                  
                  <div key={`${row.symbol}-emas`} style={{ fontSize: '0.68rem', lineHeight: '1.2' }}>
                    <div>9: {row.ema9 ? Number(row.ema9).toFixed(1) : '-'}</div>
                    <div>20: {row.ema20 ? Number(row.ema20).toFixed(1) : '-'}</div>
                  </div>,
                  
                  <span key={`${row.symbol}-volume`} className={Number(row.volume_spike) >= 2.0 ? 'tone-good' : undefined} style={{ fontWeight: Number(row.volume_spike) >= 2.0 ? 'bold' : 'normal' }}>
                    {row.volume_spike ? `${Number(row.volume_spike).toFixed(2)}x` : '-'}
                  </span>,
                  
                  <span key={`${row.symbol}-breakout`}>
                    {row.breakout_level ? Number(row.breakout_level).toFixed(2) : '-'}
                  </span>,
                  
                  <div key={`${row.symbol}-sr`} style={{ fontSize: '0.68rem', lineHeight: '1.2' }}>
                    <div>S: {row.support ? Number(row.support).toFixed(1) : '-'}</div>
                    <div>R: {row.resistance ? Number(row.resistance).toFixed(1) : '-'}</div>
                  </div>,
                  
                  <div key={`${row.symbol}-targets`} style={{ fontSize: '0.68rem', lineHeight: '1.2' }}>
                    <div>T1: {row.target1 ? Number(row.target1).toFixed(2) : '-'}</div>
                    <div>T2: {row.target2 ? Number(row.target2).toFixed(2) : '-'}</div>
                  </div>,
                  
                  <span key={`${row.symbol}-sl`}>
                    {row.stop_loss ? Number(row.stop_loss).toFixed(2) : '-'}
                  </span>,
                  
                  <span key={`${row.symbol}-expprog`} className="tone-good" style={{ fontFamily: 'monospace' }}>
                    {row.expected_profit_percent ? `${Number(row.expected_profit_percent).toFixed(2)}%` : '-'}
                  </span>,
                  
                  <span key={`${row.symbol}-exprisk`} className="tone-bad" style={{ fontFamily: 'monospace' }}>
                    {row.expected_loss_percent ? `${Number(row.expected_loss_percent).toFixed(2)}%` : '-'}
                  </span>,
                  
                  <span key={`${row.symbol}-rr`} className={Number(row.risk_reward_ratio) >= 1.8 ? 'tone-good' : undefined} style={{ fontWeight: Number(row.risk_reward_ratio) >= 1.8 ? 'bold' : 'normal' }}>
                    {row.risk_reward_ratio ? Number(row.risk_reward_ratio).toFixed(2) : '-'}
                  </span>,
                  
                  <div key={`${row.symbol}-score`} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span className={`status-badge ${Number(row.quality_score) >= 75 ? 'status-good' : 'status-warn'}`} style={{ fontSize: '0.65rem', padding: '1px 4px' }}>
                      {row.quality_score || '0'}
                    </span>
                    <span style={{ fontSize: '0.6rem', color: 'var(--muted)' }}>
                      {row.quality_label || ''}
                    </span>
                  </div>,
                  
                  <span key={`${row.symbol}-decision`} className={`status-badge ${decisionClass}`}>
                    {row.decision || 'WATCH'}
                  </span>,
                  
                  <span key={`${row.symbol}-reason`} style={{ fontSize: '0.68rem', whiteSpace: 'normal', display: 'inline-block', maxWidth: '180px' }}>
                    {row.reason || '-'}
                  </span>,
                  
                  <span key={`${row.symbol}-suggested`} style={{ fontSize: '0.68rem', whiteSpace: 'nowrap' }}>
                    {row.suggested_at || '-'}
                  </span>,
                  
                  <span key={`${row.symbol}-pl`} className={Number(row.pl_after_suggestion) > 0 ? 'tone-good' : Number(row.pl_after_suggestion) < 0 ? 'tone-bad' : undefined} style={{ fontWeight: row.pl_after_suggestion ? 'bold' : 'normal' }}>
                    {row.pl_after_suggestion !== null && row.pl_after_suggestion !== undefined ? `${Number(row.pl_after_suggestion).toFixed(2)}%` : '-'}
                  </span>,
                  
                  <button 
                    key={`${row.symbol}-action`} 
                    className={`btn-${isAdded ? 'secondary' : 'primary'}`} 
                    style={{ padding: '3px 8px', fontSize: '0.65rem', display: 'flex', alignItems: 'center', gap: '4px', height: '24px' }}
                    onClick={handleToggleWatchlist}
                  >
                    {isAdded ? (
                      <>
                        <Check size={12} className="tone-good" />
                        <span>Added</span>
                      </>
                    ) : (
                      <>
                        <Plus size={12} />
                        <span>Watchlist</span>
                      </>
                    )}
                  </button>
                ];
              })}
              emptyTitle="No Groww symbols match filters"
              emptyBody="Load Groww Intraday list or relax your filters to populate this analysis table."
            />
          </div>
        </div>
        {!rows.length && <p className="small">No Groww rows loaded yet. Click Fetch List.</p>}
      </TerminalPanel>

      <TerminalPanel 
        eyebrow="Filtered Output" 
        title="Shared Intraday Engine Results"
        actions={
          <select 
            value={displayLimit} 
            onChange={(event) => setDisplayLimit(Number(event.target.value))}
            style={{ padding: '2px 4px', fontSize: '0.74rem', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '3px' }}
          >
            <option value={10}>Top 10</option>
            <option value={20}>Top 20</option>
            <option value={50}>Top 50</option>
          </select>
        }
      >
        <StockGrid items={filteredResultRows.slice(0, displayLimit)} loading={scanning && !filteredResultRows.length} pageSize={10} />
        {filteredResultRows.length > 0 && (
          <div className="terminal-actions">
            <Link className="btn-secondary" href="/dashboard">Open Dashboard Monitor</Link>
            <Link className="btn-secondary" href="/intraday">Open Intraday Page</Link>
          </div>
        )}
      </TerminalPanel>
    </main>
  );
}
