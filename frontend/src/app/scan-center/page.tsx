"use client";
import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { Pause, Play, RotateCcw, Settings2, SlidersHorizontal, Square, Zap } from 'lucide-react';
import { getActiveScans, getScanStatus, getScanSummaries, pauseScan, resumeScan, startScan, stopAllScans, stopScan } from '@/lib/api';
import { useRealtime } from '@/hooks/useRealtime';
import { setScans, updateProgress } from '@/state/scanSlice';
import { RootState } from '@/state/store';
import { useToast } from '@/components/layout/ToastProvider';
import { DataTable, MetricTile, PageHero, ProgressLine, TerminalPanel } from '@/components/terminal/TerminalPrimitives';
import { scanTypes } from '@/lib/terminalData';

const defaultScanPresets: Record<string, Record<string, string>> = {
  Premarket: {
    period: '5d',
    interval: '5m',
    gap: '>= 1%',
    volume: '>= 2x avg',
    risk: '<= 55',
    rr: '>= 1.5R',
    stop: 'Opening range / swing low-high',
    target: 'T1 1R / T2 2R',
  },
  Intraday: {
    period: '6mo',
    interval: '15m',
    vwap: 'Required',
    volume: '>= 1.5x avg',
    risk: '<= 50',
    rr: '>= 2R',
    stop: 'Recent swing low/high',
    target: 'T1 1R / T2 2R',
  },
  Swing: {
    period: '1y',
    interval: '1d',
    trend: 'Uptrend or base breakout',
    support: '<= 3%',
    risk: '<= 50',
    rr: '>= 2R',
    stop: 'Swing low / invalidation',
    target: 'T1 1R / T2 2R',
  },
  Watchlist: {
    period: '6mo',
    interval: '1d',
    risk: '<= 55',
    rr: '>= 1.5R',
    stop: 'Recent swing level',
    target: 'T1 1R / T2 2R',
  },
  'Sector Scan': {
    period: '6mo',
    interval: '1d',
    breadth: 'Sector outperforming',
    risk: '<= 60',
    rr: '>= 1.5R',
    stop: 'Sector support invalidation',
    target: 'Relative-strength extension',
  },
  'Industry Scan': {
    period: '6mo',
    interval: '1d',
    breadth: 'Industry outperforming',
    risk: '<= 60',
    rr: '>= 1.5R',
    stop: 'Industry support invalidation',
    target: 'Relative-strength extension',
  },
  'Full NSE Scan': {
    period: '6mo',
    interval: '1d',
    pool: 'All NSE',
    screened: '97',
    selected: '35',
    final: '10',
    risk: '<= 60',
    rr: '>= 1.5R',
  },
  'Custom Scan': {
    period: '6mo',
    interval: '1d',
    screened: '97',
    selected: '35',
    final: '10',
    risk: '<= 55',
    rr: '>= 2R',
  },
};

function formatRemainingTime(seconds: number | undefined | null) {
  if (seconds === undefined || seconds === null || seconds < 0) return 'Estimating...';
  if (seconds === 0) return 'Completed';
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins > 0) {
    return `${mins}m ${secs}s left`;
  }
  return `${secs}s left`;
}

const defaultV4Filters = {
  minExpectedReturnPct: 5,
  minMlProbability: 62,
  minRiskReward: 1.8,
  maxStopDistancePct: 5,
  minDataReliabilityScore: 35,
  minProfitabilityScore: 18,
  candidatePool: 97,
  validationPool: 35,
  topN: 20,
  workers: 5,
  notifyTelegram: false,
};

export default function ScanCenterPage() {
  const dispatch = useDispatch();
  const toast = useToast();
  const scans = useSelector((state: RootState) => state.scan.scans);
  const savedSettings = useSelector((state: RootState) => state.settings.data);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState('Premarket');
  const [activeScanId, setActiveScanId] = useState<string | null>(null);
  const [activeStatus, setActiveStatus] = useState<any>(null);
  const [activeScans, setActiveScans] = useState<any[]>([]);
  const [scanPresets, setScanPresets] = useState<Record<string, Record<string, string>>>(defaultScanPresets);
  const [v4Filters, setV4Filters] = useState(defaultV4Filters);
  const [customSymbolText, setCustomSymbolText] = useState('');
  const [watchlistSymbolText, setWatchlistSymbolText] = useState('');
  const [showV4Filters, setShowV4Filters] = useState(false);
  const scanListInFlightRef = React.useRef(false);
  const scanListFailuresRef = React.useRef(0);
  const activeStatusFailuresRef = React.useRef(0);

  useEffect(() => {
    setV4Filters((current) => ({
      ...current,
      candidatePool: Number(savedSettings.custom_candidate_pool || current.candidatePool),
      validationPool: Number(savedSettings.custom_validation_pool || current.validationPool),
      topN: Number(savedSettings.custom_final_pool || current.topN),
      workers: Number(savedSettings.custom_workers || current.workers),
      minMlProbability: Number(savedSettings.ml_threshold || current.minMlProbability),
      minRiskReward: Number(savedSettings.swing_min_rr || current.minRiskReward),
      notifyTelegram: Boolean(savedSettings.notify_telegram ?? current.notifyTelegram),
    }));
  }, [savedSettings]);

  function normalizeSymbolToken(value: string) {
    const cleaned = value.trim().replace(/\s+/g, '').toUpperCase();
    if (!cleaned) return '';
    if (cleaned.includes('.')) return cleaned;
    return `${cleaned}.NS`;
  }

  function parseSymbols(value: string) {
    return Array.from(new Set(
      value
        .split(/[\s,;]+/)
        .map(normalizeSymbolToken)
        .filter(Boolean),
    ));
  }

  function normalizeSymbolText(value: string) {
    return parseSymbols(value).join(', ');
  }

  const activeSymbolText = selected === 'Watchlist' ? watchlistSymbolText : customSymbolText;
  const activeSymbols = parseSymbols(activeSymbolText);
  const needsManualSymbols = selected === 'Custom Scan' || selected === 'Watchlist';

  useEffect(() => {
    async function load() {
      if (scanListInFlightRef.current) return;
      scanListInFlightRef.current = true;
      try {
        const [summaries, active] = await Promise.all([getScanSummaries(), getActiveScans()]);
        scanListFailuresRef.current = 0;
        dispatch(setScans(summaries));
        const activeList = active.active_scans || active.scans || [];
        setActiveScans(activeList);
        
        setActiveScanId(currentId => {
          if (activeList.length > 0) {
            const exists = activeList.some((s: any) => s.scan_id === currentId);
            if (exists) {
              const match = activeList.find((s: any) => s.scan_id === currentId);
              setActiveStatus(match);
              return currentId;
            } else {
              const firstActive = activeList[0];
              setActiveStatus(firstActive);
              return firstActive.scan_id;
            }
          } else {
            setActiveStatus(null);
            return null;
          }
        });
      } catch (err) {
        scanListFailuresRef.current += 1;
        if (scanListFailuresRef.current === 3) {
          toast?.push('Backend scan sync is delayed; keeping last known scan status', 'warning');
        }
      } finally {
        setLoading(false);
        scanListInFlightRef.current = false;
      }
    }
    load();
    const timer = window.setInterval(load, 2500);
    return () => window.clearInterval(timer);
  }, [dispatch, toast]);

  useEffect(() => {
    if (!activeScanId) return;
    let cancelled = false;

    async function pollActiveScan() {
      try {
        const status = await getScanStatus(activeScanId as string);
        if (cancelled) return;
        activeStatusFailuresRef.current = 0;
        setActiveStatus(status);
        dispatch(updateProgress({ [activeScanId as string]: status }));

        if (['completed', 'error', 'cancelled'].includes(status.status)) {
          if (status.result?.status === 'error' || status.status === 'error') {
            toast?.push(status.result?.message || status.message || 'Backend scan finished with an error', 'error');
          }
          setActiveScanId(null);
          const summaries = await getScanSummaries();
          if (!cancelled) dispatch(setScans(summaries));
        }
      } catch {
        activeStatusFailuresRef.current += 1;
        if (!cancelled && activeStatusFailuresRef.current === 3) {
          toast?.push('Active scan detail is delayed; still tracking from backend summary', 'warning');
        }
      }
    }

    pollActiveScan();
    const timer = window.setInterval(pollActiveScan, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [activeScanId, dispatch, toast]);

  useRealtime((msg) => {
    if (msg?.type === 'scan.update') dispatch(updateProgress({ [msg.payload?.scan_id]: msg.payload }));
  });

  async function handleStart() {
    const preset = scanPresets[selected] || scanPresets['Custom Scan'];
    const symbols = needsManualSymbols ? activeSymbols : [];
    if (needsManualSymbols && !symbols.length) {
      toast?.push(`Enter at least one stock for ${selected}`, 'warning');
      return;
    }
    const isFastIntraday = selected === 'Intraday';
    try {
      const result = await startScan({
        symbols,
        scan_mode: selected.toLowerCase().replace(/\s+/g, '-'),
        auto_nse_universe: !symbols.length && (selected === 'Full NSE Scan' || selected === 'Premarket'),
        period: preset.period || '6mo',
        interval: preset.interval || '1d',
        top_n: v4Filters.topN,
        candidate_pool: v4Filters.candidatePool,
        validation_pool: isFastIntraday ? 0 : v4Filters.validationPool,
        strict_shortlist: !isFastIntraday,
        workers: isFastIntraday ? Math.min(3, Math.max(1, symbols.length || 3)) : v4Filters.workers,
        min_expected_return_pct: v4Filters.minExpectedReturnPct,
        min_ml_probability: v4Filters.minMlProbability,
        min_risk_reward: v4Filters.minRiskReward,
        max_stop_distance_pct: v4Filters.maxStopDistancePct,
        min_data_reliability_score: v4Filters.minDataReliabilityScore,
        min_profitability_score: v4Filters.minProfitabilityScore,
        market_open_analysis: selected === 'Premarket' || selected === 'Intraday',
        notify_telegram: v4Filters.notifyTelegram,
        telegram_category: selected,
        options: { ...preset, symbols },
      });
      setActiveScanId(result.scan_id);
      setActiveStatus(result);
      setActiveScans((current) => [result, ...current]);
      toast?.push(`${result.display_name || selected} scan started`, 'success');
    } catch {
      toast?.push('Backend scan start failed', 'error');
    }
  }

  function handlePresetChange(key: string, value: string) {
    setScanPresets((current) => ({
      ...current,
      [selected]: {
        ...(current[selected] || {}),
        [key]: value,
      },
    }));
  }

  function handleResetPreset() {
    setScanPresets((current) => ({
      ...current,
      [selected]: { ...(defaultScanPresets[selected] || defaultScanPresets['Custom Scan']) },
    }));
    toast?.push(`${selected} defaults restored`, 'success');
  }

  function handleV4FilterChange(key: keyof typeof defaultV4Filters, value: number | boolean) {
    setV4Filters((current) => ({
      ...current,
      [key]: value,
    }));
  }

  function handleActiveSymbolTextChange(value: string) {
    if (selected === 'Watchlist') setWatchlistSymbolText(value);
    else setCustomSymbolText(value);
  }

  function applyActiveSymbolNormalization() {
    const normalized = normalizeSymbolText(activeSymbolText);
    handleActiveSymbolTextChange(normalized);
    toast?.push(normalized ? `Normalized ${parseSymbols(normalized).length} symbols` : 'No symbols to normalize', normalized ? 'success' : 'warning');
  }

  function clearActiveSymbols() {
    handleActiveSymbolTextChange('');
  }

  function resetV4Filters() {
    setV4Filters(defaultV4Filters);
    toast?.push('V4 filters restored', 'success');
  }

  async function handleStop(scanId?: string) {
    const targetId = scanId || activeScanId;
    if (!targetId) return;
    try {
      await stopScan(targetId as string);
      toast?.push('Stop request sent to backend', 'success');
      setActiveScans((current) =>
        current.map((s) => (s.scan_id === targetId ? { ...s, status: 'cancelled' } : s))
      );
      if (activeScanId === targetId) {
        setActiveStatus((current: any) => (current ? { ...current, status: 'cancelled' } : null));
      }
    } catch {
      toast?.push('Unable to stop active scan', 'error');
    }
  }

  async function handleStopAll() {
    try {
      const result = await stopAllScans();
      setActiveScans([]);
      setActiveScanId(null);
      setActiveStatus(null);
      toast?.push(`Stopped ${result.stopped_count || 0} active scans`, 'success');
    } catch {
      toast?.push('Unable to stop all active scans', 'error');
    }
  }

  async function handlePause(scanId?: string) {
    const targetId = scanId || activeScanId;
    if (!targetId) return;
    try {
      await pauseScan(targetId as string);
      toast?.push('Pause request sent to backend', 'success');
      setActiveScans((current) =>
        current.map((s) =>
          s.scan_id === targetId ? { ...s, status: 'paused', pause_requested: true } : s
        )
      );
      if (activeScanId === targetId) {
        setActiveStatus((current: any) =>
          current ? { ...current, status: 'paused', pause_requested: true } : null
        );
      }
    } catch {
      toast?.push('Unable to pause active scan', 'error');
    }
  }

  async function handleResume(scanId?: string) {
    const targetId = scanId || activeScanId;
    if (!targetId) return;
    try {
      await resumeScan(targetId as string);
      toast?.push('Resume request sent to backend', 'success');
      setActiveScans((current) =>
        current.map((s) =>
          s.scan_id === targetId ? { ...s, status: 'running', pause_requested: false } : s
        )
      );
      if (activeScanId === targetId) {
        setActiveStatus((current: any) =>
          current ? { ...current, status: 'running', pause_requested: false } : null
        );
      }
    } catch {
      toast?.push('Unable to resume active scan', 'error');
    }
  }

  const latestScan = scans[0] || null;
  const activeResult = activeStatus?.result;
  const visibleResult = activeResult || latestScan;
  const visibleMessage = activeResult?.message || latestScan?.message || 'Ready for next scan';
  const symbolsScanned = visibleResult?.symbols_scanned ?? 0;
  const candidates = visibleResult?.candidates_considered ?? 0;
  const qualified = visibleResult?.summary?.qualified ?? visibleResult?.qualified ?? 0;
  const currentStage = activeStatus?.status || (latestScan ? latestScan.message || 'Last scan saved' : 'Ready for scan');
  const activeProgress = activeStatus?.status === 'running' ? 10 : activeStatus?.status === 'paused' ? 10 : latestScan ? 100 : 0;

  const rows = scans.map((scan: any) => [
    scan.scan_id || scan.id,
    scan.scan_mode || scan.type || 'Backend Scan',
    scan.message || scan.status || 'saved',
    String(scan.qualified ?? scan.symbols_scanned ?? 0),
    scan.created_at || '-',
  ]);

  return (
    <main>
      <PageHero
        eyebrow="Scan Center"
        title="Scanner V4"
        description="High-profit stock discovery with strict shortlist controls, validation pools, data-quality gates, and live backend task control."
        actions={<>
          <button className="btn-secondary" type="button" onClick={() => setShowV4Filters(!showV4Filters)}><Settings2 size={16} /> {showV4Filters ? 'Hide V4 Filters' : 'Configure V4 Filters'}</button>
          <button className="btn-primary" onClick={handleStart}><Play size={16} /> Start Scan</button>
        </>}
        metrics={[
          { label: 'Queue', value: String(scans.length) },
          { label: 'Active Scans', value: String(activeScans.length), tone: activeScans.length ? 'good' : 'warn' },
          { label: 'Min Profit', value: `${v4Filters.minExpectedReturnPct}%`, tone: 'good' },
        ]}
      />

      {showV4Filters && (
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
          <div className="form-grid" style={{ margin: 0 }}>
            <label className="field"><span>Minimum Profit %</span><input type="number" min={0} max={50} step={0.5} value={v4Filters.minExpectedReturnPct} onChange={(event) => handleV4FilterChange('minExpectedReturnPct', Number(event.target.value))} /></label>
            <label className="field"><span>Minimum ML %</span><input type="number" min={0} max={100} step={1} value={v4Filters.minMlProbability} onChange={(event) => handleV4FilterChange('minMlProbability', Number(event.target.value))} /></label>
            <label className="field"><span>Minimum R:R</span><input type="number" min={0} max={10} step={0.1} value={v4Filters.minRiskReward} onChange={(event) => handleV4FilterChange('minRiskReward', Number(event.target.value))} /></label>
            <label className="field"><span>Max Stop %</span><input type="number" min={0} max={30} step={0.5} value={v4Filters.maxStopDistancePct} onChange={(event) => handleV4FilterChange('maxStopDistancePct', Number(event.target.value))} /></label>
            <label className="field"><span>Data Quality %</span><input type="number" min={0} max={100} step={1} value={v4Filters.minDataReliabilityScore} onChange={(event) => handleV4FilterChange('minDataReliabilityScore', Number(event.target.value))} /></label>
            <label className="field"><span>Profitability Score</span><input type="number" min={0} max={100} step={1} value={v4Filters.minProfitabilityScore} onChange={(event) => handleV4FilterChange('minProfitabilityScore', Number(event.target.value))} /></label>
            <label className="field"><span>Candidate Pool</span><input type="number" min={25} max={500} step={5} value={v4Filters.candidatePool} onChange={(event) => handleV4FilterChange('candidatePool', Number(event.target.value))} /></label>
            <label className="field"><span>Validation Pool</span><input type="number" min={5} max={100} step={5} value={v4Filters.validationPool} onChange={(event) => handleV4FilterChange('validationPool', Number(event.target.value))} /></label>
            <label className="field"><span>Final Rows</span><input type="number" min={5} max={50} step={1} value={v4Filters.topN} onChange={(event) => handleV4FilterChange('topN', Number(event.target.value))} /></label>
            <label className="field"><span>Workers</span><input type="number" min={1} max={12} step={1} value={v4Filters.workers} onChange={(event) => handleV4FilterChange('workers', Number(event.target.value))} /></label>
            <label className="field field--inline"><span>Telegram</span><input type="checkbox" checked={v4Filters.notifyTelegram} onChange={(event) => handleV4FilterChange('notifyTelegram', event.target.checked)} /></label>
          </div>
          <div className="terminal-actions" style={{ marginTop: '8px', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '6px' }}>
            <button className="btn-primary" onClick={handleStart}><SlidersHorizontal size={13} /> Run V4 Filter</button>
            <button className="btn-secondary" onClick={resetV4Filters}><RotateCcw size={13} /> Reset V4</button>
          </div>
        </div>
      )}

      <div className="terminal-grid" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        <TerminalPanel eyebrow="Scan Types" title="Priority Launcher">
          <div className="control-grid">
            {scanTypes.map((type) => (
              <button key={type} className={selected === type ? 'choice-card active' : 'choice-card'} onClick={() => setSelected(type)}>
                {type}
              </button>
            ))}
          </div>
          <div className="preset-grid">
            {Object.entries(scanPresets[selected] || scanPresets['Custom Scan']).map(([key, value]) => (
              <label className="preset-pill preset-pill--editable" key={key}>
                <span>{key}</span>
                <input value={value} onChange={(event) => handlePresetChange(key, event.target.value)} />
              </label>
            ))}
          </div>
          {needsManualSymbols && (
            <div className="symbol-editor">
              <label className="field field--wide">
                <span>{selected === 'Watchlist' ? 'Watchlist Stocks' : 'Custom Stocks'}</span>
                <textarea
                  value={activeSymbolText}
                  onBlur={applyActiveSymbolNormalization}
                  onChange={(event) => handleActiveSymbolTextChange(event.target.value)}
                  placeholder="Enter stocks separated by comma or space"
                  rows={4}
                />
              </label>
              <div className="symbol-editor__actions">
                <button className="btn-secondary" type="button" onClick={applyActiveSymbolNormalization}>Normalize .NS</button>
                <button className="btn-secondary" type="button" onClick={clearActiveSymbols}>Clear</button>
                <span>{activeSymbols.length ? `${activeSymbols.length} ready: ${activeSymbols.slice(0, 6).join(', ')}${activeSymbols.length > 6 ? '...' : ''}` : 'No stocks entered'}</span>
              </div>
            </div>
          )}
          <div className="terminal-actions">
            <button className="btn-primary" onClick={handleStart}><Play size={15} /> Start</button>
            <button className="btn-secondary" onClick={handleResetPreset}><RotateCcw size={15} /> Reset Defaults</button>
            <button className="btn-secondary" onClick={() => handlePause()} disabled={!activeScanId || activeStatus?.status === 'paused'}><Pause size={15} /> Pause</button>
            <button className="btn-secondary" onClick={() => handleResume()} disabled={!activeScanId || activeStatus?.status !== 'paused'}><RotateCcw size={15} /> Resume</button>
            <button className="btn-secondary" onClick={() => handleStop()} disabled={!activeScanId}><Square size={15} /> Stop Selected</button>
            <button className="btn-secondary" onClick={handleStopAll} disabled={!activeScans.length}><Square size={15} /> Stop All Active</button>
          </div>
        </TerminalPanel>

        <TerminalPanel eyebrow="Live Monitoring" title="Backend Task Status">
          <div className="metric-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', marginBottom: '16px' }}>
            <MetricTile label="Active Scans" value={activeScans.length} detail={activeScans.length ? 'multiple scans can run together' : visibleMessage} icon={Zap} tone={activeScans.length ? 'good' : latestScan ? 'info' : 'warn'} />
            <MetricTile label="Symbols Scanned" value={symbolsScanned} detail="from backend scan record" tone={symbolsScanned ? 'good' : 'warn'} />
            <MetricTile label="Candidates" value={candidates} detail="from backend scan record" tone={candidates ? 'good' : 'warn'} />
            <MetricTile label="Qualified" value={qualified} detail="from backend summary" tone={qualified ? 'good' : 'warn'} />
          </div>

          {/* Detailed Selected Scan Card */}
          {activeStatus && (
            <div style={{
              background: 'var(--surface-2)',
              border: '1px solid var(--border-strong)',
              borderRadius: '8px',
              padding: '20px',
              marginBottom: '20px',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
              boxShadow: 'var(--shadow)',
              position: 'relative',
              overflow: 'hidden'
            }}>
              <div style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '4px',
                height: '100%',
                background: activeStatus.status === 'running' ? 'var(--success)' : activeStatus.status === 'paused' ? 'var(--warning)' : 'var(--danger)'
              }} />
              
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
                <div>
                  <span style={{ fontSize: '0.68rem', textTransform: 'uppercase', fontWeight: 800, letterSpacing: '0.08em', color: 'var(--accent-2)' }}>Selected Active Scan Control</span>
                  <h3 style={{ margin: '4px 0 0 0', fontSize: '1.25rem', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '10px' }}>
                    {activeStatus.display_name || activeStatus.scan_type || 'Active Scan'}
                    <span style={{
                      fontSize: '0.72rem',
                      fontFamily: 'monospace',
                      background: 'rgba(255,255,255,0.06)',
                      border: '1px solid var(--border)',
                      padding: '2px 8px',
                      borderRadius: '4px',
                      color: 'var(--muted)'
                    }}>{activeStatus.scan_id}</span>
                  </h3>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  {activeStatus.status === 'running' && (
                    <button className="btn-secondary" style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem', minHeight: '32px' }} onClick={() => handlePause(activeStatus.scan_id)}>
                      <Pause size={14} /> Pause
                    </button>
                  )}
                  {activeStatus.status === 'paused' && (
                    <button className="btn-secondary" style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem', minHeight: '32px' }} onClick={() => handleResume(activeStatus.scan_id)}>
                      <Play size={14} /> Resume
                    </button>
                  )}
                  {['running', 'paused', 'queued'].includes(activeStatus.status) && (
                    <button className="btn-secondary" style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem', minHeight: '32px', background: 'rgba(239, 68, 68, 0.2)', border: '1px solid rgba(239, 68, 68, 0.4)', color: '#fff' }} onClick={() => handleStop(activeStatus.scan_id)}>
                      <Square size={14} /> Terminate
                    </button>
                  )}
                </div>
              </div>

              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                gap: '16px',
                borderTop: '1px solid var(--border)',
                borderBottom: '1px solid var(--border)',
                padding: '16px 0',
                background: 'rgba(255,255,255,0.01)',
                borderRadius: '4px'
              }}>
                <div style={{ padding: '0 12px' }}>
                  <span style={{ display: 'block', fontSize: '0.68rem', color: 'var(--muted)', fontWeight: 800, textTransform: 'uppercase' }}>Status</span>
                  <strong className={
                    activeStatus.status === 'running' ? 'status-good' : activeStatus.status === 'paused' ? 'status-warn' : 'status-bad'
                  } style={{ display: 'inline-block', marginTop: '4px', fontSize: '1rem', textTransform: 'uppercase' }}>
                    {activeStatus.status}
                  </strong>
                </div>
                <div style={{ padding: '0 12px', borderLeft: '1px solid var(--border)' }}>
                  <span style={{ display: 'block', fontSize: '0.68rem', color: 'var(--muted)', fontWeight: 800, textTransform: 'uppercase' }}>Started At</span>
                  <span style={{ display: 'inline-block', marginTop: '4px', fontSize: '0.9rem', fontWeight: 700 }}>{activeStatus.created_at || '-'}</span>
                </div>
                <div style={{ padding: '0 12px', borderLeft: '1px solid var(--border)' }}>
                  <span style={{ display: 'block', fontSize: '0.68rem', color: 'var(--muted)', fontWeight: 800, textTransform: 'uppercase' }}>Estimated Remaining</span>
                  <span style={{ display: 'inline-block', marginTop: '4px', fontSize: '0.9rem', fontWeight: 700, color: 'var(--accent)' }}>
                    {formatRemainingTime(activeStatus.remaining_seconds)}
                  </span>
                </div>
                <div style={{ padding: '0 12px', borderLeft: '1px solid var(--border)' }}>
                  <span style={{ display: 'block', fontSize: '0.68rem', color: 'var(--muted)', fontWeight: 800, textTransform: 'uppercase' }}>Current Progress</span>
                  <span style={{ display: 'inline-block', marginTop: '4px', fontSize: '0.9rem', fontWeight: 700 }}>{activeStatus.progress ?? 0}%</span>
                </div>
              </div>

              <div>
                <span style={{ display: 'block', fontSize: '0.68rem', color: 'var(--muted)', fontWeight: 800, textTransform: 'uppercase', marginBottom: '6px' }}>Current Activity Stage</span>
                <ProgressLine value={activeStatus.progress ?? 0} label={activeStatus.status_message || activeStatus.message || 'Scanning stock universe...'} />
              </div>
            </div>
          )}

          <div style={{ marginTop: '10px' }}>
            <DataTable
              columns={['Scan Type', 'Status', 'Progress', 'Remaining Time', 'Started', 'Actions']}
              rows={activeScans.map((scan: any) => [
                scan.display_name || scan.scan_type || 'Scan',
                <span key={`${scan.scan_id}-status`} className={
                  scan.status === 'running' ? 'status-good' : scan.status === 'paused' ? 'status-warn' : 'status-bad'
                } style={{ fontWeight: 800 }}>{scan.status}</span>,
                <span key={`${scan.scan_id}-progress`} style={{ fontWeight: 700 }}>{scan.progress ?? 0}%</span>,
                <span key={`${scan.scan_id}-remaining`} style={{ color: 'var(--accent)', fontWeight: 700 }}>{formatRemainingTime(scan.remaining_seconds)}</span>,
                scan.created_at || '-',
                <div key={`${scan.scan_id}-actions`} style={{ display: 'flex', gap: '6px' }}>
                  <button className="btn-secondary" style={{ padding: '4px 10px', fontSize: '0.75rem', minHeight: '26px' }} onClick={() => { setActiveScanId(scan.scan_id); setActiveStatus(scan); }}>
                    Details
                  </button>
                  {scan.status === 'running' && (
                    <button className="btn-secondary" style={{ padding: '4px 8px', fontSize: '0.75rem', minHeight: '26px' }} onClick={() => handlePause(scan.scan_id)} title="Pause Scan">
                      <Pause size={12} />
                    </button>
                  )}
                  {scan.status === 'paused' && (
                    <button className="btn-secondary" style={{ padding: '4px 8px', fontSize: '0.75rem', minHeight: '26px' }} onClick={() => handleResume(scan.scan_id)} title="Resume Scan">
                      <Play size={12} />
                    </button>
                  )}
                  {['running', 'paused', 'queued'].includes(scan.status) && (
                    <button className="btn-secondary" style={{ padding: '4px 8px', fontSize: '0.75rem', minHeight: '26px', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', color: '#fff' }} onClick={() => handleStop(scan.scan_id)} title="Terminate Scan">
                      <Square size={12} />
                    </button>
                  )}
                </div>
              ])}
            />
          </div>
        </TerminalPanel>
      </div>

      <TerminalPanel eyebrow="Queue" title="Saved Backend Scans">
        <DataTable columns={['Scan ID', 'Type', 'Status', 'Qualified / Scanned', 'Created']} rows={rows} />
        {loading && <p className="small">Loading scan queue...</p>}
      </TerminalPanel>
    </main>
  );
}
