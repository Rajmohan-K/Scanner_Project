"use client";
import React, { useMemo, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { Activity, Crosshair, Pin, Play, ScanLine, Star, TrendingUp } from 'lucide-react';
import StockGrid from '@/components/molecules/LazyStockGrid';
import { getActiveScans, getLatestScanWithResults, getQuickIntradaySignal, getV20Quote, sendTelegramStockAlert, startScan } from '@/lib/api';
import { useRealtime } from '@/hooks/useRealtime';
import { setTopStocks } from '@/state/dashboardSlice';
import { RootState } from '@/state/store';
import { useToast } from '@/components/layout/ToastProvider';
import { DataTable, MetricTile, PageHero, TerminalPanel, Toolbar } from '@/components/terminal/TerminalPrimitives';
import { addStocksToLiveMonitor } from '@/lib/liveMonitor';
import { GROWW_EVENT, readGrowwResults } from '@/lib/growwIntraday';

export default function IntradayPage() {
  const dispatch = useDispatch();
  const toast = useToast();
  const [pushed, setPushed] = useState<any[]>([]);
  const [query, setQuery] = useState('');
  const [view, setView] = useState('Table');
  const [scans, setScans] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [displayLimit, setDisplayLimit] = useState(10);
  const [activeScans, setActiveScans] = useState<any[]>([]);
  const [customSymbols, setCustomSymbols] = useState('RELIANCE.NS, TCS.NS');
  const [period, setPeriod] = useState('30d');
  const [interval, setIntervalValue] = useState('15m');
  const [selectedMonitor, setSelectedMonitor] = useState<any[]>([]);
  const [growwRows, setGrowwRows] = useState<any[]>([]);
  const [growwUpdatedAt, setGrowwUpdatedAt] = useState('');
  const [telegramAlerts, setTelegramAlerts] = useState(false);
  const [quickSignalLoading, setQuickSignalLoading] = useState(false);
  const [quickSignalError, setQuickSignalError] = useState('');
  const alertedSymbols = React.useRef<Set<string>>(new Set());
  const sourceRef = React.useRef<any[]>([]);
  const visibleQuotesRefreshingRef = React.useRef(false);
  const lastQuickSignalRef = React.useRef('');
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
      const payload = await getQuickIntradaySignal(normalized, interval);
      const row = payload?.row;
      if (!row) throw new Error('No signal returned');
      setPushed((current) => [row, ...current.filter((item: any) => symbolOf(item) !== row.symbol && symbolOf(item) !== row.stock)].slice(0, 25));
      dispatch(setTopStocks([row, ...topStocks.filter((item: any) => symbolOf(item) !== row.symbol && symbolOf(item) !== row.stock)]));
      if (showToast) toast?.push(`${row.symbol || normalized} quick signal: ${row.signal || row.trade_type}`, 'success');
      return row;
    } catch {
      setQuickSignalError(`Quick intraday signal unavailable for ${normalized}`);
      if (showToast) toast?.push(`Quick intraday signal unavailable for ${normalized}`, 'error');
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
    const symbols = normalizeSymbolsInput(customSymbols);
    if (symbols.length !== 1) return;
    const symbol = symbols[0];
    if (symbol === lastQuickSignalRef.current) return;
    const timer = window.setTimeout(() => {
      lastQuickSignalRef.current = symbol;
      runQuickIntradaySignal(symbol);
    }, 450);
    return () => window.clearTimeout(timer);
  }, [customSymbols, interval]);

  React.useEffect(() => {
    async function loadLatest() {
      try {
        const data = await getLatestScanWithResults({ scanMode: 'intraday-custom', actionableOnly: false, source: 'filtered' });
        dispatch(setTopStocks(data.rows));
        setScans(data.scans || []);
      } catch {
        dispatch(setTopStocks([]));
      }
    }
    loadLatest();
    const timer = window.setInterval(loadLatest, 1000);
    return () => window.clearInterval(timer);
  }, [dispatch]);

  React.useEffect(() => {
    async function loadActiveScans() {
      try {
        const data = await getActiveScans();
        const rows = data.active_scans || data.scans || [];
        const intradayRows = rows.filter((scan: any) => /intraday/i.test(`${scan.scan_type} ${scan.payload?.scan_mode}`));
        setActiveScans(intradayRows);
        setLoading(intradayRows.length > 0);
      } catch {
        setActiveScans([]);
      }
    }
    loadActiveScans();
    const timer = window.setInterval(loadActiveScans, 1000);
    return () => window.clearInterval(timer);
  }, []);

  useRealtime((msg) => {
    if (msg?.type === 'push-to-intraday') {
      setPushed((prev) => [...(msg.payload || []), ...prev]);
      toast?.push('New intraday candidate received', 'success');
    }
    if (msg?.type === 'scan-result') dispatch(setTopStocks(msg.payload?.results || []));
  });

  const source = pushed.length ? pushed : topStocks;
  const displayItems = useMemo(() => source.filter((stock: any) => `${stock.symbol} ${stock.stock} ${stock.sector}`.toLowerCase().includes(query.toLowerCase())), [source, query]);
  const visibleItems = useMemo(() => displayItems.slice(0, displayLimit), [displayItems, displayLimit]);
  const visibleQuoteSymbols = useMemo(() => visibleItems.slice(0, Math.min(displayLimit, 25)).map((stock: any) => stock.symbol || stock.stock).filter(Boolean), [visibleItems, displayLimit]);
  const visibleQuoteSymbolsKey = visibleQuoteSymbols.join('|');
  React.useEffect(() => {
    sourceRef.current = source;
  }, [source]);
  React.useEffect(() => {
    if (!visibleQuoteSymbols.length) return;
    async function refreshVisibleQuotes() {
      if (visibleQuotesRefreshingRef.current) return;
      visibleQuotesRefreshingRef.current = true;
      try {
        const quotes = await Promise.all(visibleQuoteSymbols.map(async (symbol) => {
          try {
            const payload = await getV20Quote(symbol);
            const quote = payload?.quote || {};
            const live = Number(quote.current_price ?? quote.regularMarketPrice ?? quote.price ?? 0);
            const previous = Number(quote.previous_close || 0);
            return { symbol, live: Number.isFinite(live) && live > 0 ? Math.round(live * 100) / 100 : undefined, change: previous && live ? Math.round(((live - previous) / previous) * 10000) / 100 : undefined };
          } catch {
            return { symbol };
          }
        }));
        const bySymbol = new Map(quotes.filter((item) => item.live !== undefined).map((item) => [item.symbol, item]));
        if (!bySymbol.size) return;
        const next = sourceRef.current.map((stock: any) => {
          const symbol = stock.symbol || stock.stock;
          const item = bySymbol.get(symbol);
          return item ? { ...stock, live_price: item.live, current_price: item.live, change_pct: item.change ?? stock.change_pct, last_updated: new Date().toISOString() } : stock;
        });
        if (pushed.length) setPushed(next);
        else dispatch(setTopStocks(next));
      } finally {
        visibleQuotesRefreshingRef.current = false;
      }
    }
    refreshVisibleQuotes();
    const timer = window.setInterval(refreshVisibleQuotes, 1000);
    return () => window.clearInterval(timer);
  }, [dispatch, pushed.length, visibleQuoteSymbolsKey]);
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

      <div className="metric-grid">
        <MetricTile label="Breakouts" value={breakoutCount} detail="from backend breakout analysis" icon={TrendingUp} tone={breakoutCount ? 'good' : 'warn'} />
        <MetricTile label="VWAP Reclaims" value={vwapCount} detail="from backend VWAP analysis" icon={Crosshair} tone={vwapCount ? 'good' : 'warn'} />
        <MetricTile label="Risk Alerts" value={riskAlerts} detail="from backend risk model" icon={Activity} tone={riskAlerts ? 'warn' : 'good'} />
        <MetricTile label="Manual Scans" value={intradayScanCount} detail="from backend scan queue" icon={ScanLine} tone={intradayScanCount ? 'good' : 'warn'} />
      </div>

      <TerminalPanel eyebrow="Custom Intraday Scan" title="Selected Stocks Scanner">
        <div className="scan-entry-grid">
          <label className="field field--wide">
            <span>Stocks To Scan</span>
            <textarea value={customSymbols} onChange={(event) => setCustomSymbols(event.target.value)} placeholder="Enter live symbols separated by commas" rows={3} />
          </label>
          <label className="field">
            <span>Period</span>
            <select value={period} onChange={(event) => setPeriod(event.target.value)}><option>5d</option><option>30d</option><option>60d</option><option>3mo</option><option>6mo</option><option>1y</option></select>
          </label>
          <label className="field">
            <span>Interval</span>
            <select value={interval} onChange={(event) => setIntervalValue(event.target.value)}><option>5m</option><option>15m</option><option>1h</option><option>1d</option></select>
          </label>
          <label className="field">
            <span>Stop Loss Method</span>
            <select value={filters.stopMethod} onChange={(event) => setFilters((current) => ({ ...current, stopMethod: event.target.value }))}><option>Recent swing low/high</option><option>1.2x ATR</option><option>VWAP rejection</option><option>Previous candle low/high</option></select>
          </label>
          <label className="field">
            <span>Target Plan</span>
            <select value={filters.targetPlan} onChange={(event) => setFilters((current) => ({ ...current, targetPlan: event.target.value }))}><option>T1 1R / T2 2R</option><option>T1 pivot / T2 day high-low</option><option>T1 0.8R / T2 1.5R</option></select>
          </label>
          <div className="field field--actions">
            <span>Action</span>
            <button className="btn-primary" onClick={handleRunCustomScan}><Play size={15} /> {loading ? 'Start Another' : 'Run Intraday Scan'}</button>
          </div>
        </div>
        {quickSignalLoading && <p className="small status-good">Analyzing single stock immediately...</p>}
        {quickSignalError && <p className="small status-bad">{quickSignalError}</p>}
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
          <div className="quick-pick-list">
            {growwRows.slice(0, 12).map((stock: any) => {
              const symbol = symbolOf(stock);
              return (
                <button key={`groww-${symbol}`} className="choice-card" onClick={() => addToMonitor(stock)}>
                  <Pin size={14} /> {symbol}
                </button>
              );
            })}
          </div>
          <StockGrid items={growwRows} loading={false} />
        </TerminalPanel>
        <TerminalPanel eyebrow="Section A" title="Latest Intraday Custom Filtered Stocks">
          <Toolbar search={query} setSearch={setQuery} tabs={['Table', 'List']} activeTab={view} onTabChange={setView} />
          <div className="quick-pick-list">
            {visibleItems.slice(0, 12).map((stock: any) => {
              const symbol = symbolOf(stock);
              return (
                <button key={symbol} className="choice-card" onClick={() => addToMonitor(stock)}>
                  <Pin size={14} /> {symbol}
                </button>
              );
            })}
          </div>
          <StockGrid items={visibleItems} loading={loading && !visibleItems.length} />
        </TerminalPanel>
        <TerminalPanel eyebrow="Section B" title="Manual Custom Scan">
          <div className="form-grid">
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
          <div className="terminal-actions">
            <select value={displayLimit} onChange={(event) => setDisplayLimit(Number(event.target.value))}><option value={10}>Top 10</option><option value={25}>Top 25</option></select>
            <button className="btn-primary"><Star size={15} /> Apply Filters</button>
            <button className="btn-secondary">Reset</button>
          </div>
        </TerminalPanel>
      </div>
    </main>
  );
}
