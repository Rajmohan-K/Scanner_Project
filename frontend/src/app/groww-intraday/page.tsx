"use client";
import React, { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Activity, Clock, ExternalLink, Play, RefreshCw, Send, UploadCloud } from 'lucide-react';
import StockGrid from '@/components/molecules/LazyStockGrid';
import { getGrowwIntradayStocks } from '@/lib/api';
import { useToast } from '@/components/layout/ToastProvider';
import { DataTable, MetricTile, PageHero, TerminalPanel } from '@/components/terminal/TerminalPrimitives';
import { defaultGrowwSettings, GROWW_EVENT, GrowwAutoSettings, pushSymbolsToIntraday, readGrowwResults, readGrowwSettings, runGrowwIntradayAnalysis, writeGrowwSettings } from '@/lib/growwIntraday';

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

  const symbols = useMemo(() => Array.from(new Set(rows.filter((row) => row.symbol).map((row) => row.symbol))), [rows]);
  const unresolved = rows.filter((row) => !row.resolved);

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
    if (!symbols.length) {
      toast.push('Fetch Groww symbols first', 'warning');
      return;
    }
    setScanning(true);
    setResultRows([]);
    setMessage(`Starting intraday analysis for ${symbols.length} Groww symbols...`);
    try {
      const saved = await runGrowwIntradayAnalysis(settings.limit);
      setScanId(saved.scanId);
      setResultRows(saved.rows);
      setMessage(`Analysis completed. ${saved.rows.length} filtered stocks pushed to dashboard monitor and intraday page.`);
      toast.push(`${saved.rows.length} Groww filtered stocks pushed to dashboard and intraday`, 'success');
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
        description="Fetch the Groww intraday stock list, resolve NSE symbols, run the backend intraday scanner, and push filtered stocks to Dashboard and Intraday."
        actions={<>
          <a className="btn-secondary" href="https://groww.in/stocks/intraday" target="_blank" rel="noreferrer"><ExternalLink size={16} /> Open Groww</a>
          <button className="btn-secondary" type="button" onClick={fetchGroww} disabled={loading}><RefreshCw size={16} /> {loading ? 'Fetching' : 'Fetch List'}</button>
          <button className="btn-primary" type="button" onClick={runGrowwScan} disabled={scanning || loading || !symbols.length}><Play size={16} /> {scanning ? 'Analyzing' : 'Analyze Intraday'}</button>
        </>}
        metrics={[
          { label: 'Resolved Symbols', value: String(symbols.length), tone: symbols.length ? 'good' : 'warn' },
          { label: 'Unresolved Names', value: String(unresolved.length), tone: unresolved.length ? 'warn' : 'good' },
          { label: 'Scan ID', value: scanId || 'Not started' },
          { label: 'Auto Check', value: settings.enabled ? `${settings.intervalMinutes} min` : 'Off', tone: settings.enabled ? 'good' : 'warn' },
        ]}
      />

      <div className="metric-grid">
        <MetricTile label="Source Status" value={loading ? 'Fetching' : rows.length ? 'Loaded' : 'Waiting'} detail={message} icon={UploadCloud} tone={rows.length ? 'good' : 'warn'} />
        <MetricTile label="Analysis Status" value={scanning ? 'Running' : resultRows.length ? 'Complete' : 'Idle'} detail="backend intraday scan" icon={Activity} tone={resultRows.length ? 'good' : scanning ? 'warn' : 'info'} />
        <MetricTile label="Auto Scheduler" value={settings.enabled ? 'Enabled' : 'Disabled'} detail={`checks every ${settings.intervalMinutes} minute(s)`} icon={Clock} tone={settings.enabled ? 'good' : 'warn'} />
      </div>

      <TerminalPanel eyebrow="Automation" title="Continuous Groww Intraday Checker">
        <div className="form-grid">
          <label className="field field--inline">
            <span>Enable auto checking</span>
            <input type="checkbox" checked={settings.enabled} onChange={(event) => updateSettings({ enabled: event.target.checked })} />
          </label>
          <label className="field">
            <span>Interval Minutes</span>
            <input type="number" min={1} max={240} value={settings.intervalMinutes} onChange={(event) => updateSettings({ intervalMinutes: Number(event.target.value) || 15 })} />
          </label>
          <label className="field">
            <span>Groww Row Limit</span>
            <input type="number" min={5} max={200} value={settings.limit} onChange={(event) => updateSettings({ limit: Number(event.target.value) || 80 })} />
          </label>
        </div>
        <p className="small">When enabled, the app keeps checking Groww, runs intraday analysis after each interval, and pushes filtered stocks to Dashboard and Intraday sections.</p>
      </TerminalPanel>

      <TerminalPanel eyebrow="Groww Source" title="Resolved Intraday Symbols" actions={<>
        <button className="btn-secondary" type="button" onClick={pushWithoutScan}><Send size={15} /> Push Symbols</button>
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

      <TerminalPanel eyebrow="Filtered Output" title="Backend Intraday Analysis Results">
        <StockGrid items={resultRows} loading={scanning && !resultRows.length} pageSize={20} />
        {resultRows.length > 0 && (
          <div className="terminal-actions">
            <Link className="btn-secondary" href="/dashboard">Open Dashboard Monitor</Link>
            <Link className="btn-secondary" href="/intraday">Open Intraday Page</Link>
          </div>
        )}
      </TerminalPanel>
    </main>
  );
}
