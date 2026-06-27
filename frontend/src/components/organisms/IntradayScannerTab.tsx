"use client";
import React, { useMemo, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { Activity, Crosshair, Download, Play, ScanLine, Settings2, Star, TrendingUp } from 'lucide-react';
import StockGrid from '@/components/molecules/LazyStockGrid';
import { getActiveScans, getLatestScanWithResults, getLiveStockAnalysis, getV20Quote, sendTelegramStockAlert, startScan } from '@/lib/api';
import { useRealtime } from '@/hooks/useRealtime';
import { setTopStocks } from '@/state/dashboardSlice';
import { RootState } from '@/state/store';
import { useToast } from '@/components/layout/ToastProvider';
import { DataTable, MetricTile, PageHero, TerminalPanel, Toolbar } from '@/components/terminal/TerminalPrimitives';
import { addStocksToLiveMonitor } from '@/lib/liveMonitor';
import { GROWW_EVENT, growwSymbolsText, readGrowwResults } from '@/lib/growwIntraday';
import GrowwPriorityPanel from '@/components/organisms/GrowwPriorityPanel';
import { addPriorityCandidates, buildPriorityRows } from '@/lib/priorityPicks';
import { applyUnifiedAnalysis, hydrateRowsWithBatchQuotes, hydrateRowsWithUnifiedAnalysis } from '@/lib/unifiedAnalysis';

export default function IntradayPage() {
  const dispatch = useDispatch();
  const toast = useToast();
  const [pushed, setPushed] = useState<any[]>([]);
  const [query, setQuery] = useState('');
  const [scans, setScans] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [displayLimit, setDisplayLimit] = useState(10);
  const [activeScans, setActiveScans] = useState<any[]>([]);
  const [customSymbols, setCustomSymbols] = useState('RELIANCE.NS, TCS.NS');
  const [period, setPeriod] = useState('30d');
  const [interval, setIntervalValue] = useState('15m');
  const [selectedMonitor, setSelectedMonitor] = useState<any[]>([]);
  const [growwRows, setGrowwRows] = useState<any[]>([]);
  const [growwPriorityRows, setGrowwPriorityRows] = useState<any[]>([]);
  const [growwUpdatedAt, setGrowwUpdatedAt] = useState('');
  const [telegramAlerts, setTelegramAlerts] = useState(false);
  const [quickSignalLoading, setQuickSignalLoading] = useState(false);
  const [quickSignalError, setQuickSignalError] = useState('');
  const [selectedScanRows, setSelectedScanRows] = useState<any[]>([]);
  const [showConfig, setShowConfig] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const alertedSymbols = React.useRef<Set<string>>(new Set());
  const sourceRef = React.useRef<any[]>([]);
  const latestLoadInFlightRef = React.useRef(false);
  const activeScanInFlightRef = React.useRef(false);
  const activeScanFailuresRef = React.useRef(0);
  const visibleQuotesRefreshingRef = React.useRef(false);
  const [filters, setFilters] = useState({
    sector: 'All',
    industry: 'All',
    volume: '>= 1.5x avg',
    priceRange: '50-5000',
    mlScore: '>= 60',
    technicalScore: '>= 55',
    riskScore: '<= 50',
    rewardPotential: '>= 2R',
    stopMethod: 'Recent swing low/high',
    targetPlan: 'T1 1R / T2 2R',
    vwap: 'Required',
    breakout: 'Preferred',
  });
  const topStocks = useSelector((state: RootState) => state.dashboard.topStocks);
  const savedSettings = useSelector((state: RootState) => state.settings.data);
  const monitorStorageKey = 'intraday-monitor-symbols';
  const customSymbolsStorageKey = 'custom-intraday-symbols';

  function normalizeSymbolsInput(value: string) {
    return value
      .split(/[\s,;]+/)
      .map((symbol) => {
        const upper = symbol.trim().toUpperCase();
        return upper && !upper.includes('.') ? `${upper}.NS` : upper;
      })
      .filter(Boolean);
  }

  async function runQuickIntradaySignal(symbol: string, showToast = false) {
    const normalized = normalizeSymbolsInput(symbol)[0];
    if (!normalized) return null;
    setQuickSignalLoading(true);
    setQuickSignalError('');
    try {
      const analysis = await getLiveStockAnalysis(normalized, 'intraday');
      if (analysis.status === 'error') {
        throw new Error(analysis.message || `Stock data unavailable for ${normalized}`);
      }
      const row = applyUnifiedAnalysis({ symbol: normalized, source_name: 'Unified Intraday Analysis' }, analysis, 'intraday');
      if (!row?.symbol) throw new Error('No signal returned');
      setPushed((current) => [row, ...current.filter((item: any) => symbolOf(item) !== row.symbol && symbolOf(item) !== row.stock)].slice(0, 25));
      setSelectedScanRows((current) => [row, ...current.filter((item: any) => symbolOf(item) !== row.symbol && symbolOf(item) !== row.stock)].slice(0, 25));
      dispatch(setTopStocks([row, ...topStocks.filter((item: any) => symbolOf(item) !== row.symbol && symbolOf(item) !== row.stock)]));
      return row;
    } catch (error: any) {
      const message = error?.response?.data?.message || error?.message || `Quick intraday signal unavailable for ${normalized}`;
      const row = {
        symbol: normalized,
        stock: normalized,
        signal: 'UNAVAILABLE',
        action: 'UNAVAILABLE',
        reason: message,
        analysis_unavailable: true,
      };
      setSelectedScanRows((current) => [row, ...current.filter((item: any) => symbolOf(item) !== normalized)].slice(0, 25));
      setQuickSignalError(message);
      return null;
    } finally {
      setQuickSignalLoading(false);
    }
  }

  React.useEffect(() => {
    const saved = window.localStorage.getItem(customSymbolsStorageKey);
    if (saved) setCustomSymbols(saved);
    function handleCustomSymbols(event: Event) {
      const detail = (event as CustomEvent).detail;
      if (detail?.target === 'intraday' && Array.isArray(detail.symbols)) {
        setCustomSymbols(detail.symbols.join(', '));
      }
    }
    window.addEventListener('custom-scanner-symbols', handleCustomSymbols);
    return () => window.removeEventListener('custom-scanner-symbols', handleCustomSymbols);
  }, []);

  React.useEffect(() => {
    function syncGrowwResults() {
      const latest = readGrowwResults();
      setGrowwRows(latest.rows || []);
      setGrowwPriorityRows(latest.priorityRows || []);
      setGrowwUpdatedAt(latest.updatedAt || '');
    }
    syncGrowwResults();
    window.addEventListener(GROWW_EVENT, syncGrowwResults);
    window.addEventListener('storage', syncGrowwResults);
    return () => {
      window.removeEventListener(GROWW_EVENT, syncGrowwResults);
      window.removeEventListener('storage', syncGrowwResults);
    };
  }, []);

  React.useEffect(() => {
    window.localStorage.setItem(customSymbolsStorageKey, customSymbols);
  }, [customSymbols]);

  React.useEffect(() => {
    let active = true;
    async function loadLatest() {
      if (latestLoadInFlightRef.current) return;
      latestLoadInFlightRef.current = true;
      try {
        const data = await getLatestScanWithResults({ scanMode: /intraday|premarket|market-open|v20-dashboard|groww/i, actionableOnly: false, source: 'best', horizon: 'intraday' });
        if (!active) return;
        const rows = await hydrateRowsWithUnifiedAnalysis(data.rows || [], 'intraday', 40);
        dispatch(setTopStocks(rows));
        setScans(data.scans || []);
      } catch {
        // Keep the last visible scan rows while the backend is busy running a scan.
      } finally {
        latestLoadInFlightRef.current = false;
      }
    }
    loadLatest();
    const timer = window.setInterval(loadLatest, 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [dispatch]);

  React.useEffect(() => {
    async function updateQuotes() {
      const current = topStocks;
      if (!current.length || visibleQuotesRefreshingRef.current) return;
      visibleQuotesRefreshingRef.current = true;
      try {
        const updated = await hydrateRowsWithBatchQuotes(current);
        dispatch(setTopStocks(updated));
      } catch (err) {
        console.error("Failed to update intraday quotes:", err);
      } finally {
        visibleQuotesRefreshingRef.current = false;
      }
    }
    const timer = window.setInterval(updateQuotes, 1000);
    return () => window.clearInterval(timer);
  }, [dispatch, topStocks]);

  React.useEffect(() => {
    async function loadActiveScans() {
      if (activeScanInFlightRef.current) return;
      activeScanInFlightRef.current = true;
      try {
        const data = await getActiveScans();
        activeScanFailuresRef.current = 0;
        const rows = data.active_scans || data.scans || [];
        const intradayRows = rows.filter((scan: any) => /intraday/i.test(`${scan.scan_type} ${scan.payload?.scan_mode}`));
        setActiveScans(intradayRows);
        setLoading(intradayRows.length > 0);
      } catch {
        activeScanFailuresRef.current += 1;
      } finally {
        activeScanInFlightRef.current = false;
      }
    }
    loadActiveScans();
    const timer = window.setInterval(loadActiveScans, 2500);
    return () => window.clearInterval(timer);
  }, []);

  useRealtime((msg) => {
    if (msg?.type === 'push-to-intraday') {
      setPushed((prev) => [...(msg.payload || []), ...prev]);
      toast?.push('New intraday candidate received', 'success');
    }
    if (msg?.type === 'scan-result') {
      void hydrateRowsWithUnifiedAnalysis(msg.payload?.results || [], 'intraday', 40).then((rows) => dispatch(setTopStocks(rows)));
    }
  });

  const source = pushed.length ? pushed : topStocks;
  const displayItems = useMemo(() => source.filter((stock: any) => `${stock.symbol} ${stock.stock} ${stock.sector}`.toLowerCase().includes(query.toLowerCase())), [source, query]);
  const visibleItems = useMemo(() => displayItems.slice(0, displayLimit), [displayItems, displayLimit]);
  const selectedScannerRows = useMemo(() => {
    const symbols = normalizeSymbolsInput(customSymbols);
    const bySymbol = new Map([...selectedScanRows, ...source, ...growwRows].map((stock: any) => [symbolOf(stock), stock]));
    return symbols.map((symbol) => bySymbol.get(symbol)).filter(Boolean);
  }, [customSymbols, growwRows, selectedScanRows, source]);
  const visibleQuoteSymbols = useMemo(() => visibleItems.slice(0, Math.min(displayLimit, 25)).map((stock: any) => stock.symbol || stock.stock).filter(Boolean), [visibleItems, displayLimit]);
  const visibleQuoteSymbolsKey = visibleQuoteSymbols.join('|');
  const intradayPriorityRows = useMemo(
    () => buildPriorityRows([...growwPriorityRows, ...growwRows, ...displayItems], {
      horizon: 'intraday',
      includeUnknown: true,
      limit: 5,
      minProfitPct: 3,
      sourceName: 'Intraday Sources',
    }),
    [displayItems, growwPriorityRows, growwRows],
  );
  React.useEffect(() => {
    sourceRef.current = source;
  }, [source]);

  React.useEffect(() => {
    if (selectedMonitor.length || !source.length) return;
    try {
      const savedSymbols = JSON.parse(window.localStorage.getItem(monitorStorageKey) || '[]');
      if (!Array.isArray(savedSymbols) || !savedSymbols.length) return;
      const restored = savedSymbols
        .map((symbol: string) => source.find((stock: any) => symbolOf(stock) === symbol))
        .filter(Boolean);
      if (restored.length) setSelectedMonitor(restored);
    } catch {
      window.localStorage.removeItem(monitorStorageKey);
    }
  }, [selectedMonitor.length, source]);
  React.useEffect(() => {
    setSelectedMonitor((current) => current.map((item) => {
      const latest = source.find((stock: any) => symbolOf(stock) === symbolOf(item));
      return latest || item;
    }));
  }, [source]);
  const breakoutCount = displayItems.filter((stock: any) => {
    const breakout = stock.score_breakdown?.breakout_analysis?.raw_score;
    return Number(breakout || 0) > 0 || /breakout/i.test(`${stock.breakout_strength || ''} ${stock.pattern || ''} ${stock.reason || ''}`);
  }).length;
  const vwapCount = displayItems.filter((stock: any) => Number(stock.score_breakdown?.vwap_analysis?.raw_score || 0) > 0 || /vwap/i.test(String(stock.reason || ''))).length;
  const riskAlerts = displayItems.filter((stock: any) => Number(stock.risk_score || 0) >= 50 || /high/i.test(String(stock.risk_level || ''))).length;
  const intradayScanCount = scans.filter((scan: any) => /intraday|custom/i.test(String(scan.scan_mode || scan.type || ''))).length;
  const pnlReady = displayItems.some((stock: any) => typeof stock.live_price === 'number' && typeof stock.entry_price === 'number');

  function symbolOf(stock: any) {
    return stock.symbol || stock.stock;
  }

  function formatNumber(value: unknown, digits = 2) {
    const numeric = Number(value);
    return Number.isFinite(numeric) && numeric > 0 ? numeric.toLocaleString('en-IN', { maximumFractionDigits: digits }) : '-';
  }

  function stockPrice(stock: any) {
    return stock.live_price ?? stock.current_price ?? stock.last_close ?? stock.ltp;
  }

  function targetText(stock: any) {
    const targets = [stock.target1 ?? stock.target_1, stock.target2 ?? stock.target_2, stock.target3 ?? stock.target_3]
      .map((value) => formatNumber(value))
      .filter((value) => value !== '-');
    return targets.length ? targets.join(' / ') : '-';
  }

  function profitQualityText(stock: any) {
    const profit = stock.expected_return ?? stock.priority_profit_pct ?? stock.profit_pct ?? stock.expected_profit_pct;
    const quality = stock.quality_score ?? stock.data_reliability_score ?? stock.confidence_pct;
    const parts = [];
    if (Number(profit)) parts.push(`Exp ${formatNumber(profit, 2)}%`);
    if (Number(quality)) parts.push(`Quality ${formatNumber(quality, 0)}`);
    return parts.length ? parts.join(' / ') : '-';
  }

  function scoresText(stock: any) {
    const parts = [
      ['ML', stock.ml_score ?? stock.ml_probability],
      ['Tech', stock.technical_score],
      ['Conf', stock.confidence_pct ?? stock.confidence],
    ].map(([label, value]) => Number(value) ? `${label} ${formatNumber(value, 0)}` : '').filter(Boolean);
    return parts.length ? parts.join(' / ') : '-';
  }

  function signalText(stock: any) {
    return stock.action || stock.signal || stock.trade_type || stock.ai_rating || 'Waiting';
  }

  function reasonText(stock: any) {
    return stock.reason || stock.trade_reason || stock.priority_reason || stock.quality_filter_reasons || 'Waiting for backend analysis';
  }

  function isPriorityEligible(stock: any) {
    return buildPriorityRows([stock], { horizon: 'intraday', includeUnknown: true, limit: 3, minProfitPct: 3 }).length > 0;
  }

  function addCustomToPriority(stock: any) {
    const rows = buildPriorityRows([stock], { horizon: 'intraday', includeUnknown: true, limit: 3, minProfitPct: 3 });
    if (!rows.length) {
      toast?.push(`${symbolOf(stock)} is not eligible for profitable priority yet`, 'warning');
      return;
    }
    const result = addPriorityCandidates(rows, 'intraday');
    toast?.push(`${result.added || rows.length} profitable intraday stock(s) added to Priority Picks`, 'success');
  }

  function removeCustomSymbol(symbol: string) {
    const next = normalizeSymbolsInput(customSymbols).filter((item) => item !== symbol);
    setCustomSymbols(next.join(', '));
    setSelectedScanRows((current) => current.filter((item: any) => symbolOf(item) !== symbol));
  }

  function pullGrowwSymbolsToCustomScan() {
    const text = growwSymbolsText(80);
    if (!text) {
      toast?.push('No Groww symbols available. Fetch or analyze Groww Source first.', 'warning');
      return;
    }
    setCustomSymbols(text);
    setQuickSignalError('');
    toast?.push('Groww symbols pulled into Intraday scanner input', 'success');
  }

  function addToMonitor(stock: any) {
    const symbol = symbolOf(stock);
    if (!symbol) return;
    setSelectedMonitor((current) => {
      const next = current.some((item) => symbolOf(item) === symbol) ? current : [stock, ...current];
      window.localStorage.setItem(monitorStorageKey, JSON.stringify(next.map(symbolOf).filter(Boolean)));
      return next;
    });
    addStocksToLiveMonitor([{ ...stock, symbol }], 'intraday');
    toast?.push(`${symbol} added to intraday and dashboard live monitor`, 'success');
  }

  function removeFromMonitor(symbol: string) {
    setSelectedMonitor((current) => {
      const next = current.filter((item) => symbolOf(item) !== symbol);
      window.localStorage.setItem(monitorStorageKey, JSON.stringify(next.map(symbolOf).filter(Boolean)));
      return next;
    });
  }

  function approachStatus(stock: any) {
    const live = Number(stock.live_price || stock.last_close || 0);
    const stop = Number(stock.stop_loss || stock.stoploss || 0);
    const target = Number(stock.target1 || stock.target_1 || 0);
    if (!live) return { label: 'No live price', tone: 'status-warn' };
    if (target && live >= target) return { label: 'Target reached', tone: 'status-good' };
    if (stop && Math.abs((live - stop) / live) <= 0.01) return { label: 'Near stop loss', tone: 'status-bad' };
    if (target && Math.abs((target - live) / live) <= 0.01) return { label: 'Near target 1', tone: 'status-good' };
    return { label: 'Monitoring', tone: 'status-warn' };
  }

  React.useEffect(() => {
    if (!telegramAlerts || !selectedMonitor.length) return;
    selectedMonitor.forEach(async (stock) => {
      const symbol = symbolOf(stock);
      const status = approachStatus(stock);
      if (!symbol || alertedSymbols.current.has(symbol)) return;
      if (!/target|stop/i.test(status.label)) return;
      try {
        await sendTelegramStockAlert({
          symbol,
          status: status.label,
          telegram_category: 'Intraday',
          live_price: stock.live_price ?? stock.last_close,
          entry_price: stock.entry_price ?? stock.entry,
          stop_loss: stock.stop_loss ?? stock.stoploss,
          target1: stock.target1 ?? stock.target_1,
          target2: stock.target2 ?? stock.target_2,
        });
        alertedSymbols.current.add(symbol);
        toast?.push(`Telegram alert sent for ${symbol}`, 'success');
      } catch {
        toast?.push(`Telegram alert failed for ${symbol}`, 'error');
      }
    });
  }, [selectedMonitor, telegramAlerts, toast]);

  async function handleRunCustomScan() {
    const symbols = normalizeSymbolsInput(customSymbols);
    if (!symbols.length) {
      setQuickSignalError('Enter at least one complete NSE/BSE symbol, then run the scan.');
      return;
    }
    if (symbols.length === 1) {
      await runQuickIntradaySignal(symbols[0], true);
      return;
    }
    setLoading(true);
    try {
      const started = await startScan({
        scan_mode: 'intraday-custom',
        symbols,
        period,
        interval,
        auto_nse_universe: false,
        top_n: 20,
        candidate_pool: Math.max(Number(savedSettings.custom_candidate_pool || 97), symbols.length),
        validation_pool: 0,
        strict_shortlist: false,
        workers: Math.min(3, Math.max(1, symbols.length)),
        min_expected_return_pct: 5,
        min_ml_probability: Number(savedSettings.ml_threshold || 62),
        min_risk_reward: 1.8,
        max_stop_distance_pct: 5,
        min_data_reliability_score: 35,
        min_profitability_score: 18,
        market_open_analysis: true,
        notify_telegram: telegramAlerts,
        telegram_category: 'Intraday',
        options: filters,
      });
      setActiveScans((current) => [started, ...current]);
      toast?.push(`${started.display_name || 'Intraday'} scan started`, 'success');
    } catch {
      toast?.push('Backend intraday scan failed', 'error');
      setLoading(false);
    }
  }

  return (
    <main>
      <PageHero
        eyebrow="Intraday Scanner"
        title="Dual-Panel Live Execution Desk"
        description="Premarket qualified stocks on one side, independent custom scans on the other, with live price, P&L, timeframes, and risk signals."
        actions={<><button className="btn-primary" onClick={handleRunCustomScan}><Play size={16} /> {loading ? 'Start Another Intraday Scan' : 'Run Custom Scan'}</button><button className="btn-secondary">Save Layout</button></>}
        metrics={[
          { label: 'Live Candidates', value: String(visibleItems.length), tone: 'good' },
          { label: 'P&L Tracker', value: pnlReady ? 'Connected' : 'Waiting for entry/LTP', tone: pnlReady ? 'good' : 'warn' },
          { label: 'Feed', value: quickSignalLoading ? 'Quick signal running' : displayItems.length ? 'Latest intraday data' : 'Waiting', tone: displayItems.length ? 'good' : 'warn' },
        ]}
      />

      <GrowwPriorityPanel
        eyebrow="Intraday Priority"
        title="High Profit Intraday Priority Picks"
        rows={intradayPriorityRows}
        updatedAt={growwUpdatedAt}
        onMonitor={addToMonitor}
        emptyText="No intraday source currently has a complete 3%+ trade plan. Run Groww, custom intraday, or scanner scans to refresh candidates."
      />

      <div className="metric-grid">
        <MetricTile label="Breakouts" value={breakoutCount} detail="from backend breakout analysis" icon={TrendingUp} tone={breakoutCount ? 'good' : 'warn'} />
        <MetricTile label="VWAP Reclaims" value={vwapCount} detail="from backend VWAP analysis" icon={Crosshair} tone={vwapCount ? 'good' : 'warn'} />
        <MetricTile label="Risk Alerts" value={riskAlerts} detail="from backend risk model" icon={Activity} tone={riskAlerts ? 'warn' : 'good'} />
        <MetricTile label="Manual Scans" value={intradayScanCount} detail="from backend scan queue" icon={ScanLine} tone={intradayScanCount ? 'good' : 'warn'} />
      </div>

      <TerminalPanel 
        eyebrow="Custom Intraday Scan" 
        title="Selected Stocks Scanner"
        actions={
          <button 
            className="btn-secondary" 
            type="button" 
            onClick={() => setShowConfig(!showConfig)}
            style={{ padding: '3px 8px', fontSize: '0.72rem', minHeight: '26px' }}
          >
            {showConfig ? 'Hide Settings' : 'Configure Parameters'}
          </button>
        }
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '4px 8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase' }}>Stocks:</span>
            <input 
              value={customSymbols} 
              onChange={(event) => setCustomSymbols(event.target.value)} 
              placeholder="RELIANCE.NS, TCS.NS"
              style={{ 
                padding: '3px 6px', 
                fontSize: '0.76rem', 
                width: '300px', 
                background: 'var(--panel-strong)', 
                border: '1px solid var(--border)',
                borderRadius: '4px',
                color: 'var(--text)'
              }}
            />
            <button className="btn-secondary" type="button" onClick={pullGrowwSymbolsToCustomScan} style={{ padding: '3px 8px', fontSize: '0.72rem', minHeight: '26px' }}><Download size={11} /> Pull Groww List</button>
            <button className="btn-primary" onClick={handleRunCustomScan} style={{ padding: '3px 8px', fontSize: '0.72rem', minHeight: '26px' }}><Play size={11} /> {loading ? 'Running...' : 'Run Intraday Scan'}</button>
          </div>

          {showConfig && (
            <div style={{ 
              display: 'grid', 
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', 
              gap: '8px',
              background: 'var(--surface-3)',
              border: '1px solid var(--border)',
              borderRadius: '6px',
              padding: '10px',
              marginTop: '4px'
            }}>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '1px', fontSize: '0.65rem' }}>
                <span style={{ color: 'var(--muted)', fontWeight: 700 }}>Period</span>
                <select value={period} onChange={(event) => setPeriod(event.target.value)} style={{ padding: '2px 4px', fontSize: '0.74rem', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '4px' }}>
                  <option>5d</option><option>30d</option><option>60d</option><option>3mo</option><option>6mo</option><option>1y</option>
                </select>
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '1px', fontSize: '0.65rem' }}>
                <span style={{ color: 'var(--muted)', fontWeight: 700 }}>Interval</span>
                <select value={interval} onChange={(event) => setIntervalValue(event.target.value)} style={{ padding: '2px 4px', fontSize: '0.74rem', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '4px' }}>
                  <option>5m</option><option>15m</option><option>1h</option><option>1d</option>
                </select>
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '1px', fontSize: '0.65rem' }}>
                <span style={{ color: 'var(--muted)', fontWeight: 700 }}>Stop Loss Method</span>
                <select value={filters.stopMethod} onChange={(event) => setFilters((current) => ({ ...current, stopMethod: event.target.value }))} style={{ padding: '2px 4px', fontSize: '0.74rem', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '4px' }}>
                  <option>Recent swing low/high</option><option>1.2x ATR</option><option>VWAP rejection</option><option>Previous candle low/high</option>
                </select>
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '1px', fontSize: '0.65rem' }}>
                <span style={{ color: 'var(--muted)', fontWeight: 700 }}>Target Plan</span>
                <select value={filters.targetPlan} onChange={(event) => setFilters((current) => ({ ...current, targetPlan: event.target.value }))} style={{ padding: '2px 4px', fontSize: '0.74rem', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '4px' }}>
                  <option>T1 1R / T2 2R</option><option>T1 pivot / T2 day high-low</option><option>T1 0.8R / T2 1.5R</option>
                </select>
              </label>
            </div>
          )}
        </div>
        {quickSignalLoading && <p className="small status-good" style={{ margin: '4px 8px', fontSize: '0.72rem' }}>Analyzing single stock immediately...</p>}
        {quickSignalError && <p className="small status-bad" style={{ margin: '4px 8px', fontSize: '0.72rem' }}>{quickSignalError}</p>}
      </TerminalPanel>

      <TerminalPanel eyebrow="Selected Stocks Scanner" title="Custom Intraday Results">
        <DataTable
          columns={['Symbol', 'LTP', 'Entry', 'SL', 'Targets', 'Profit / Quality', 'Scores', 'Signal', 'Pattern / Reason', 'Actions']}
          rows={selectedScannerRows.map((stock: any) => {
            const symbol = symbolOf(stock);
            const eligible = isPriorityEligible(stock);
            return [
              <strong key={`${symbol}-symbol`}>{symbol}</strong>,
              formatNumber(stockPrice(stock)),
              formatNumber(stock.entry_price ?? stock.entry),
              formatNumber(stock.stop_loss ?? stock.stoploss),
              targetText(stock),
              profitQualityText(stock),
              scoresText(stock),
              <span key={`${symbol}-signal`} className={`signal-pill signal-pill--${String(signalText(stock)).toLowerCase().replace(/\s+/g, '-')}`}>{signalText(stock)}</span>,
              <span key={`${symbol}-reason`} className="selected-scanner-reason">{reasonText(stock)}</span>,
              <span key={`${symbol}-actions`} className="row-actions selected-scanner-actions">
                <button className="icon-button" title="Add to dashboard live monitor" type="button" onClick={() => addToMonitor(stock)}>+</button>
                <button className="icon-button" title={eligible ? 'Add to profitable Priority Picks' : 'Not eligible for profitable picks yet'} type="button" disabled={!eligible} onClick={() => addCustomToPriority(stock)}>P</button>
                <button className="icon-button" title="Remove symbol" type="button" onClick={() => removeCustomSymbol(symbol)}>x</button>
              </span>,
            ];
          })}
          emptyTitle="No selected stocks"
          emptyBody="Enter one or more symbols above. Single-symbol intraday analysis appears here immediately."
        />
      </TerminalPanel>

      <TerminalPanel eyebrow="Selected Monitor" title="Pinned Intraday Watch">
        <label className="field field--inline monitor-alert-toggle">
          <span>Telegram target/stop alerts</span>
          <input type="checkbox" checked={telegramAlerts} onChange={(event) => setTelegramAlerts(event.target.checked)} />
        </label>
        <DataTable
          columns={['Stock', 'LTP', 'Entry', 'Stop Loss', 'Target 1', 'Target 2', 'Status', 'Action']}
          rows={selectedMonitor.map((stock: any) => {
            const symbol = symbolOf(stock);
            const status = approachStatus(stock);
            return [
              <strong key={symbol}>{symbol}</strong>,
              stock.live_price ?? stock.last_close ?? '-',
              stock.entry_price ?? stock.entry ?? '-',
              stock.stop_loss ?? stock.stoploss ?? '-',
              stock.target1 ?? stock.target_1 ?? '-',
              stock.target2 ?? stock.target_2 ?? '-',
              <span key={`${symbol}-status`} className={`status-badge ${status.tone}`}>{status.label}</span>,
              <button key={`${symbol}-remove`} className="btn-secondary" onClick={() => removeFromMonitor(symbol)}>Remove</button>,
            ];
          })}
        />
        {!selectedMonitor.length && <p className="small">Select stocks from scan results to monitor live price, stop loss, and target approach.</p>}
      </TerminalPanel>

      <div className="terminal-grid intraday-layout">
        <TerminalPanel eyebrow="Groww Auto Source" title="Groww Intraday Filtered Signals">
          <p className="small">
            {growwUpdatedAt ? `Last Groww analysis: ${new Date(growwUpdatedAt).toLocaleString('en-IN')}` : 'No Groww auto analysis yet. Enable it from Groww Source.'}
          </p>
          <StockGrid items={growwRows} loading={false} onPinStock={addToMonitor} pinLabel="Pin to intraday monitor" />
        </TerminalPanel>
        <TerminalPanel 
          eyebrow="Dual-Panel Scanner" 
          title="Latest Intraday Custom Filtered Stocks"
          actions={
            <button 
              className="btn-secondary" 
              type="button" 
              onClick={() => setShowFilters(!showFilters)}
              style={{ padding: '3px 8px', fontSize: '0.72rem', minHeight: '26px' }}
            >
              <Settings2 size={13} /> {showFilters ? 'Hide Filters' : 'Configure Filters'}
            </button>
          }
        >
          <Toolbar search={query} setSearch={setQuery} />
          {showFilters && (
            <div style={{
              background: 'var(--surface-3)',
              border: '1px solid var(--border)',
              borderRadius: '6px',
              padding: '10px',
              marginTop: '4px',
              marginBottom: '8px'
            }}>
              <div className="form-grid" style={{ margin: 0 }}>
                <label className="field"><span>Sector</span><input value={filters.sector} onChange={(event) => setFilters((current) => ({ ...current, sector: event.target.value }))} /></label>
                <label className="field"><span>Industry</span><input value={filters.industry} onChange={(event) => setFilters((current) => ({ ...current, industry: event.target.value }))} /></label>
                <label className="field"><span>Volume</span><select value={filters.volume} onChange={(event) => setFilters((current) => ({ ...current, volume: event.target.value }))}><option>{'>= 1.5x avg'}</option><option>{'>= 2x avg'}</option><option>{'>= 3x avg'}</option></select></label>
                <label className="field"><span>Price Range</span><input value={filters.priceRange} onChange={(event) => setFilters((current) => ({ ...current, priceRange: event.target.value }))} /></label>
                <label className="field"><span>ML Score</span><select value={filters.mlScore} onChange={(event) => setFilters((current) => ({ ...current, mlScore: event.target.value }))}><option>{'>= 55'}</option><option>{'>= 60'}</option><option>{'>= 70'}</option></select></label>
                <label className="field"><span>Technical Score</span><select value={filters.technicalScore} onChange={(event) => setFilters((current) => ({ ...current, technicalScore: event.target.value }))}><option>{'>= 50'}</option><option>{'>= 55'}</option><option>{'>= 65'}</option></select></label>
                <label className="field"><span>Risk Score</span><select value={filters.riskScore} onChange={(event) => setFilters((current) => ({ ...current, riskScore: event.target.value }))}><option>{'<= 35'}</option><option>{'<= 50'}</option><option>{'<= 65'}</option></select></label>
                <label className="field"><span>Reward Potential</span><select value={filters.rewardPotential} onChange={(event) => setFilters((current) => ({ ...current, rewardPotential: event.target.value }))}><option>{'>= 1.5R'}</option><option>{'>= 2R'}</option><option>{'>= 3R'}</option></select></label>
                <label className="field"><span>VWAP Filter</span><select value={filters.vwap} onChange={(event) => setFilters((current) => ({ ...current, vwap: event.target.value }))}><option>Required</option><option>Preferred</option><option>Ignore</option></select></label>
                <label className="field"><span>Breakout Filter</span><select value={filters.breakout} onChange={(event) => setFilters((current) => ({ ...current, breakout: event.target.value }))}><option>Required</option><option>Preferred</option><option>Pullback allowed</option></select></label>
              </div>
              <div className="terminal-actions" style={{ marginTop: '8px', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '6px' }}>
                <select value={displayLimit} onChange={(event) => setDisplayLimit(Number(event.target.value))}><option value={10}>Top 10</option><option value={25}>Top 25</option></select>
                <button className="btn-primary" type="button"><Star size={13} /> Apply Filters</button>
                <button className="btn-secondary" type="button">Reset</button>
              </div>
            </div>
          )}
          <StockGrid items={displayItems} loading={loading && !displayItems.length} pageSize={displayLimit} onPinStock={addToMonitor} pinLabel="Pin to intraday monitor" />
        </TerminalPanel>
      </div>
    </main>
  );
}
