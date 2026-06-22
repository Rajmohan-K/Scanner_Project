"use client";
import React, { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Activity, Clock, ExternalLink, Play, RefreshCw, Send, Settings2, UploadCloud } from 'lucide-react';
import StockGrid from '@/components/molecules/LazyStockGrid';
import { getGrowwIntradayStocks, getV20Quote } from '@/lib/api';
import { useToast } from '@/components/layout/ToastProvider';
import { DataTable, MetricTile, PageHero, TerminalPanel } from '@/components/terminal/TerminalPrimitives';
import { defaultGrowwSettings, GROWW_EVENT, GROWW_PRIORITY_UPDATED_EVENT, GrowwAutoSettings, pushSymbolsToIntraday, readGrowwPriorityActive, readGrowwPriorityHistory, readGrowwResults, readGrowwSettings, runGrowwIntradayAnalysis, writeGrowwPriorityActive, writeGrowwPriorityHistory, writeGrowwSettings } from '@/lib/growwIntraday';
import GrowwPriorityPanel from '@/components/organisms/GrowwPriorityPanel';

type GrowwRow = { company: string; symbol: string; resolved: boolean; candidates?: string[]; source?: string };

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

  const symbols = useMemo(() => Array.from(new Set(rows.filter((row) => row.symbol).map((row) => row.symbol))), [rows]);
  const filteredResultRows = useMemo(() => {
    return resultRows.filter((row) => row.action && row.action !== 'AVOID');
  }, [resultRows]);
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
        const closedRows: any[] = [];
        const nextActive = await Promise.all(rows.map(async (row) => {
          try {
            const payload = await getV20Quote(row.symbol);
            const quote = payload?.quote || {};
            const live = Number(quote.current_price ?? quote.regularMarketPrice ?? quote.price ?? quote.last_close ?? row.live_price ?? row.last_price ?? 0);
            if (!Number.isFinite(live) || live <= 0) return row;
            
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
              return null;
            }
            return enriched;
          } catch {
            return row;
          }
        }));
        
        const cleanActive = nextActive.filter(Boolean);
        if (closedRows.length) {
          const nextHistory = [...closedRows, ...historyRowsRef.current].slice(0, 500);
          writeGrowwPriorityHistory(nextHistory);
          setHistoryPriorityRows(nextHistory);
          
          closedRows.forEach((closedRow) => {
            toast.push(`Groww Priority: ${closedRow.symbol} moved to history (${closedRow.status === 'target_hit' ? 'Target hit' : 'Stoploss hit'})`, 'success');
          });
        }
        
        if (cleanActive.length !== rows.length) {
          writeGrowwPriorityActive(cleanActive);
          setActivePriorityRows(cleanActive);
        }
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

      <TerminalPanel eyebrow="Groww Source" title="Resolved Intraday Symbols" actions={<>
        <button className="btn-secondary" type="button" onClick={pushWithoutScan}><Send size={15} /> Send to Intraday Input</button>
      </>}>
        <DataTable
          columns={['Company', 'Resolved Symbol', 'Candidates']}
          rows={(rows.length ? rows : []).slice(0, 80).map((row) => [
            <strong key={`${row.company}-name`}>{row.company}</strong>,
            row.symbol || <span className="status-badge status-warn">Needs mapping</span>,
            row.candidates?.join(', ') || '-',
          ])}
        />
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
