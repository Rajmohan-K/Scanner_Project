"use client";
import React, { useMemo, useState } from 'react';
import { useSelector } from 'react-redux';
import { CalendarClock, Pin, LineChart, Play, Settings2, ShieldCheck, Target } from 'lucide-react';
import StockGrid from '@/components/molecules/LazyStockGrid';
import { RootState } from '@/state/store';
import { getActiveScans, getLatestScanWithResults, getV20Quote, sendTelegramStockAlert, startScan } from '@/lib/api';
import { useDispatch } from 'react-redux';
import { setTopStocks } from '@/state/dashboardSlice';
import { DataTable, MetricTile, PageHero, TerminalPanel, Toolbar } from '@/components/terminal/TerminalPrimitives';
import { useToast } from '@/components/layout/ToastProvider';
import { addStocksToLiveMonitor } from '@/lib/liveMonitor';
import GrowwPriorityPanel from '@/components/organisms/GrowwPriorityPanel';
import { addPriorityCandidates, buildPriorityRows } from '@/lib/priorityPicks';
import { hydrateRowsWithUnifiedAnalysis } from '@/lib/unifiedAnalysis';

export default function SwingPage() {
  const dispatch = useDispatch();
  const toast = useToast();
  const topStocks = useSelector((state: RootState) => state.dashboard.topStocks);
  const savedSettings = useSelector((state: RootState) => state.settings.data);
  const [query, setQuery] = useState('');
  const [customSymbols, setCustomSymbols] = useState('RELIANCE.NS, TCS.NS');
  const [loading, setLoading] = useState(false);
  const [showScanParams, setShowScanParams] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [displayLimit, setDisplayLimit] = useState(10);
  const [activeScans, setActiveScans] = useState<any[]>([]);
  const [selectedMonitor, setSelectedMonitor] = useState<any[]>([]);
  const [monitorInput, setMonitorInput] = useState('');
  const [telegramAlerts, setTelegramAlerts] = useState(false);
  const [selectedScanRows, setSelectedScanRows] = useState<any[]>([]);
  const alertedSymbols = React.useRef<Set<string>>(new Set());
  const priorityPushedSymbolsRef = React.useRef<Set<string>>(new Set());
  const topStocksRef = React.useRef<any[]>([]);
  const latestLoadInFlightRef = React.useRef(false);
  const activeScanInFlightRef = React.useRef(false);
  const activeScanFailuresRef = React.useRef(0);
  const visibleQuotesRefreshingRef = React.useRef(false);
  const [filters, setFilters] = useState({
    trend: 'Uptrend or base breakout',
    supportDistance: '<= 3%',
    minRr: '>= 2R',
    riskScore: '<= 50',
    holdingWindow: '2-10 sessions',
    stopMethod: 'Swing low / resistance invalidation',
    targetPlan: 'T1 1R / T2 2R',
    fundamentals: 'Positive or neutral',
  });
  const monitorStorageKey = 'swing-monitor-symbols';
  const customSymbolsStorageKey = 'custom-swing-symbols';

  function normalizeSymbolsInput(value: string) {
    return value.split(/[\s,;]+/).map((symbol) => {
      const upper = symbol.trim().toUpperCase();
      return upper && !upper.includes('.') ? `${upper}.NS` : upper;
    }).filter(Boolean);
  }

  React.useEffect(() => {
    const saved = window.localStorage.getItem(customSymbolsStorageKey);
    if (saved) setCustomSymbols(saved);
    function handleCustomSymbols(event: Event) {
      const detail = (event as CustomEvent).detail;
      if (detail?.target === 'swing' && Array.isArray(detail.symbols)) {
        setCustomSymbols(detail.symbols.join(', '));
      }
    }
    window.addEventListener('custom-scanner-symbols', handleCustomSymbols);
    return () => window.removeEventListener('custom-scanner-symbols', handleCustomSymbols);
  }, []);

  React.useEffect(() => {
    window.localStorage.setItem(customSymbolsStorageKey, customSymbols);
  }, [customSymbols]);

  React.useEffect(() => {
    async function loadLatest() {
      if (latestLoadInFlightRef.current) return;
      latestLoadInFlightRef.current = true;
      try {
        const data = await getLatestScanWithResults({ scanMode: /swing|v20-dashboard/i, actionableOnly: false, source: 'best', horizon: 'swing' });
        const rows = await hydrateRowsWithUnifiedAnalysis(data.rows || [], 'swing', 40);
        dispatch(setTopStocks(rows));
      } catch {
        // Keep the last visible swing rows while the backend catches up.
      } finally {
        latestLoadInFlightRef.current = false;
      }
    }
    loadLatest();
    const timer = window.setInterval(loadLatest, 3000);
    return () => window.clearInterval(timer);
  }, [dispatch]);
  React.useEffect(() => {
    async function loadActiveScans() {
      if (activeScanInFlightRef.current) return;
      activeScanInFlightRef.current = true;
      try {
        const data = await getActiveScans();
        activeScanFailuresRef.current = 0;
        const rows = data.active_scans || data.scans || [];
        const swingRows = rows.filter((scan: any) => /swing/i.test(`${scan.scan_type} ${scan.payload?.scan_mode}`));
        setActiveScans(swingRows);
        setLoading(swingRows.length > 0);
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
  const source = topStocks;
  const swingItems = useMemo(() => source.filter((item: any) => `${item.symbol} ${item.stock} ${item.sector}`.toLowerCase().includes(query.toLowerCase())), [source, query]);
  const visibleSwingItems = useMemo(() => swingItems.slice(0, displayLimit), [swingItems, displayLimit]);
  const selectedScannerRows = useMemo(() => {
    const symbols = normalizeSymbolsInput(customSymbols);
    const bySymbol = new Map([...selectedScanRows, ...source, ...selectedMonitor].map((stock: any) => [symbolOf(stock), stock]));
    return symbols.map((symbol) => bySymbol.get(symbol) || { symbol, stock: symbol });
  }, [customSymbols, selectedMonitor, selectedScanRows, source]);
  const visibleQuoteSymbols = useMemo(() => visibleSwingItems.slice(0, Math.min(displayLimit, 25)).map((stock: any) => stock.symbol || stock.stock).filter(Boolean), [visibleSwingItems, displayLimit]);
  const visibleQuoteSymbolsKey = visibleQuoteSymbols.join('|');
  const swingPriorityRows = useMemo(
    () => buildPriorityRows(swingItems, {
      horizon: 'swing',
      includeUnknown: true,
      limit: 5,
      minProfitPct: 3,
      sourceName: 'Swing Sources',
    }),
    [swingItems],
  );
  React.useEffect(() => {
    topStocksRef.current = topStocks;
  }, [topStocks]);
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
        dispatch(setTopStocks(topStocksRef.current.map((stock: any) => {
          const symbol = stock.symbol || stock.stock;
          const item = bySymbol.get(symbol);
          return item ? { ...stock, live_price: item.live, current_price: item.live, change_pct: item.change ?? stock.change_pct, last_updated: new Date().toISOString() } : stock;
        })));
      } finally {
        visibleQuotesRefreshingRef.current = false;
      }
    }
    refreshVisibleQuotes();
    const timer = window.setInterval(refreshVisibleQuotes, 1000);
    return () => window.clearInterval(timer);
  }, [dispatch, visibleQuoteSymbolsKey]);
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
  React.useEffect(() => {
    const profitable = buildPriorityRows(selectedMonitor, {
      horizon: 'swing',
      includeUnknown: true,
      limit: 5,
      minProfitPct: 3,
      sourceName: 'Swing Monitor',
    });
    const fresh = profitable.filter((row: any) => {
      const symbol = symbolOf(row);
      return symbol && !priorityPushedSymbolsRef.current.has(symbol);
    });
    if (!fresh.length) return;
    fresh.forEach((row: any) => priorityPushedSymbolsRef.current.add(symbolOf(row)));
    addPriorityCandidates(fresh, 'swing');
    toast?.push(`${fresh.length} profitable swing monitor stock(s) added to Priority Picks`, 'success');
  }, [selectedMonitor, toast]);
  const avgRr = useMemo(() => {
    const values = swingItems.map((item: any) => Number(item.rrr || item.risk_reward || 0)).filter((value) => Number.isFinite(value) && value > 0);
    return values.length ? (values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(2) : 'No setups';
  }, [swingItems]);
  const trendAligned = swingItems.filter((item: any) => /bull|uptrend|breakout/i.test(`${item.trend || ''} ${item.reason || ''}`)).length;
  const riskValidated = swingItems.filter((item: any) => Number(item.risk_score || 100) <= 50).length;
  const targetsReady = swingItems.filter((item: any) => item.target1 || item.target_1).length;

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
    const quality = stock.quality_score ?? stock.fundamental_score ?? stock.confidence_pct;
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
    return buildPriorityRows([stock], { horizon: 'swing', includeUnknown: true, limit: 3, minProfitPct: 3 }).length > 0;
  }

  function addCustomToPriority(stock: any) {
    const rows = buildPriorityRows([stock], { horizon: 'swing', includeUnknown: true, limit: 3, minProfitPct: 3 });
    if (!rows.length) {
      toast?.push(`${symbolOf(stock)} is not eligible for profitable priority yet`, 'warning');
      return;
    }
    const result = addPriorityCandidates(rows, 'swing');
    toast?.push(`${result.added || rows.length} profitable swing stock(s) added to Priority Picks`, 'success');
  }

  function removeCustomSymbol(symbol: string) {
    const next = normalizeSymbolsInput(customSymbols).filter((item) => item !== symbol);
    setCustomSymbols(next.join(', '));
    setSelectedScanRows((current) => current.filter((item: any) => symbolOf(item) !== symbol));
  }

  function addToMonitor(stock: any) {
    const symbol = symbolOf(stock);
    if (!symbol) return;
    setSelectedMonitor((current) => {
      const next = current.some((item) => symbolOf(item) === symbol) ? current : [stock, ...current];
      window.localStorage.setItem(monitorStorageKey, JSON.stringify(next.map(symbolOf).filter(Boolean)));
      return next;
    });
    addStocksToLiveMonitor([{ ...stock, symbol }], 'swing');
    toast?.push(`${symbol} added to swing and dashboard live monitor`, 'success');
  }

  function addManualMonitorSymbols() {
    const symbols = normalizeSymbolsInput(monitorInput);
    if (!symbols.length) {
      toast?.push('Enter at least one symbol to monitor', 'warning');
      return;
    }
    const rows = symbols.map((symbol) => source.find((stock: any) => symbolOf(stock) === symbol) || { symbol, stock: symbol });
    setSelectedMonitor((current) => {
      const bySymbol = new Map(current.map((row: any) => [symbolOf(row), row]));
      rows.forEach((row) => bySymbol.set(symbolOf(row), row));
      const next = Array.from(bySymbol.values()).filter((row) => symbolOf(row));
      window.localStorage.setItem(monitorStorageKey, JSON.stringify(next.map(symbolOf).filter(Boolean)));
      return next;
    });
    addStocksToLiveMonitor(rows, 'swing');
    setMonitorInput(symbols.join(', '));
    toast?.push(`${symbols.length} symbol(s) added to swing monitor`, 'success');
  }

  function pushMonitorToPriority() {
    const profitable = buildPriorityRows(selectedMonitor, {
      horizon: 'swing',
      includeUnknown: true,
      limit: 5,
      minProfitPct: 3,
      sourceName: 'Swing Monitor',
    });
    if (!profitable.length) {
      toast?.push('No selected swing monitor stocks currently meet priority rules', 'warning');
      return;
    }
    const result = addPriorityCandidates(profitable, 'swing');
    toast?.push(`${result.added || profitable.length} swing priority candidate(s) sent to Priority Picks`, 'success');
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
    if (stop && Math.abs((live - stop) / live) <= 0.02) return { label: 'Near stop loss', tone: 'status-bad' };
    if (target && Math.abs((target - live) / live) <= 0.02) return { label: 'Near target', tone: 'status-good' };
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
          telegram_category: 'Swing',
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

  async function handleRunSwingScan() {
    const symbols = normalizeSymbolsInput(customSymbols);
    setLoading(true);
    try {
      const started = await startScan({
        scan_mode: 'swing-custom',
        symbols,
        period: savedSettings.swing_period || '1y',
        interval: '1d',
        auto_nse_universe: false,
        top_n: 20,
        candidate_pool: Math.max(Number(savedSettings.custom_candidate_pool || 97), symbols.length),
        validation_pool: Math.max(Number(savedSettings.custom_validation_pool || 35), symbols.length),
        strict_shortlist: true,
        workers: 5,
        min_expected_return_pct: 5,
        min_ml_probability: Number(savedSettings.ml_threshold || 62),
        min_risk_reward: Number(savedSettings.swing_min_rr || 1.8),
        max_stop_distance_pct: 5,
        min_data_reliability_score: 35,
        min_profitability_score: 18,
        notify_telegram: telegramAlerts,
        telegram_category: 'Swing',
        options: filters,
      });
      setActiveScans((current) => [started, ...current]);
      setSelectedScanRows(symbols.map((symbol) => source.find((stock: any) => symbolOf(stock) === symbol) || { symbol, stock: symbol }));
      toast?.push(`${started.display_name || 'Swing'} scan started`, 'success');
    } catch {
      toast?.push('Backend swing scan failed', 'error');
      setLoading(false);
    }
  }

  return (
    <main>
      <PageHero
        eyebrow="Swing Scanner"
        title="Multi-Day Opportunity Workbench"
        description="Trend filters, support-resistance, pattern recognition, ML prediction, and risk planning for intermediate horizon setups."
        actions={<><button className="btn-primary" onClick={handleRunSwingScan}><Play size={16} /> {loading ? 'Start Another Swing Scan' : 'Run Swing Scan'}</button><button className="btn-secondary">Create Alert</button></>}
        metrics={[
          { label: 'Setups', value: String(visibleSwingItems.length), tone: 'good' },
          { label: 'Avg R:R', value: avgRr, tone: swingItems.length ? 'good' : 'warn' },
          { label: 'Holding Window', value: '1D-10D' },
        ]}
      />

      <GrowwPriorityPanel
        eyebrow="Swing Priority"
        title="High Profit Swing Priority Picks"
        rows={swingPriorityRows}
        onMonitor={addToMonitor}
        emptyText="No swing source currently has a complete 3%+ trade plan. Run swing scans or custom swing analysis to refresh candidates."
      />

      <div className="metric-grid">
        <MetricTile label="Trend Aligned" value={trendAligned} detail="from multi-timeframe analysis" icon={LineChart} tone={trendAligned ? 'good' : 'warn'} />
        <MetricTile label="Risk Validated" value={riskValidated} detail="from risk model" icon={ShieldCheck} tone={riskValidated ? 'good' : 'warn'} />
        <MetricTile label="Targets Ready" value={targetsReady} detail="from target engine" icon={Target} tone={targetsReady ? 'good' : 'warn'} />
        <MetricTile label="Review Cadence" value="Daily" detail="from swing settings" icon={CalendarClock} tone="info" />
      </div>

      <TerminalPanel 
        eyebrow="Custom Swing Scan" 
        title="Selected Stocks Scanner"
        actions={
          <button 
            className="btn-secondary" 
            type="button" 
            onClick={() => setShowScanParams(!showScanParams)}
            style={{ padding: '3px 8px', fontSize: '0.72rem', minHeight: '26px' }}
          >
            {showScanParams ? 'Hide Settings' : 'Configure Parameters'}
          </button>
        }
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '4px 8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase' }}>Stocks To Scan:</span>
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
            <button className="btn-primary" onClick={handleRunSwingScan} style={{ padding: '3px 8px', fontSize: '0.72rem', minHeight: '26px' }}><Play size={11} /> {loading ? 'Running...' : 'Run Swing Scan'}</button>
          </div>

          {showScanParams && (
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
                <span style={{ color: 'var(--muted)', fontWeight: 700 }}>Stop Loss Method</span>
                <select value={filters.stopMethod} onChange={(event) => setFilters((current) => ({ ...current, stopMethod: event.target.value }))} style={{ padding: '2px 4px', fontSize: '0.74rem', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '4px' }}>
                  <option>Swing low / resistance invalidation</option>
                  <option>1.5x ATR</option>
                  <option>20 EMA close invalidation</option>
                </select>
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '1px', fontSize: '0.65rem' }}>
                <span style={{ color: 'var(--muted)', fontWeight: 700 }}>Target Plan</span>
                <select value={filters.targetPlan} onChange={(event) => setFilters((current) => ({ ...current, targetPlan: event.target.value }))} style={{ padding: '2px 4px', fontSize: '0.74rem', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '4px' }}>
                  <option>T1 1R / T2 2R</option>
                  <option>T1 resistance / T2 measured move</option>
                  <option>T1 1.5R / T2 3R</option>
                </select>
              </label>
            </div>
          )}
        </div>
      </TerminalPanel>

      <TerminalPanel eyebrow="Selected Stocks Scanner" title="Custom Swing Results">
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
          emptyBody="Enter one or more symbols above. Swing scan results for those symbols appear here when backend analysis is available."
        />
      </TerminalPanel>

      <TerminalPanel
        eyebrow="Selected Monitor"
        title="Pinned Swing Watch"
        actions={<button className="btn-secondary" type="button" onClick={pushMonitorToPriority}>Add Profitable To Priority</button>}
      >
        <div className="live-monitor-entry">
          <label className="field field--wide">
            <span>Add Stocks To Swing Monitor</span>
            <input value={monitorInput} onBlur={() => setMonitorInput(normalizeSymbolsInput(monitorInput).join(', '))} onChange={(event) => setMonitorInput(event.target.value)} placeholder="RELIANCE, TCS, INFY" />
          </label>
          <button className="btn-primary" type="button" onClick={addManualMonitorSymbols}>Add Monitor</button>
        </div>
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
              <span key={`${symbol}-actions`} className="row-actions">
                <button className="icon-button" title="Add profitable setup to Priority Picks" type="button" onClick={() => addPriorityCandidates([stock], 'swing')}>+</button>
                <button className="icon-button" title="Remove" type="button" onClick={() => removeFromMonitor(symbol)}>x</button>
              </span>,
            ];
          })}
        />
        {!selectedMonitor.length && <p className="small">Select swing candidates to monitor stop loss and target approach.</p>}
      </TerminalPanel>

      <TerminalPanel 
        eyebrow="Dual-Panel Scanner" 
        title="Latest Swing Custom Filtered Stocks"
        actions={
          <button 
            className="btn-secondary" 
            type="button" 
            onClick={() => setShowFilters(!showFilters)}
            style={{ padding: '3px 8px', fontSize: '0.72rem', minHeight: '26px' }}
          >
            {showFilters ? 'Hide Filters' : 'Configure Filters'}
          </button>
        }
      >
        <Toolbar search={query} setSearch={setQuery} />
        {showFilters && (
          <div className="form-grid">
            <label className="field"><span>Trend Filter</span><select value={filters.trend} onChange={(event) => setFilters((current) => ({ ...current, trend: event.target.value }))}><option>Uptrend or base breakout</option><option>Pullback to support</option><option>RS outperformer</option></select></label>
            <label className="field"><span>Support Distance</span><select value={filters.supportDistance} onChange={(event) => setFilters((current) => ({ ...current, supportDistance: event.target.value }))}><option>{'<= 2%'}</option><option>{'<= 3%'}</option><option>{'<= 5%'}</option></select></label>
            <label className="field"><span>Minimum R:R</span><select value={filters.minRr} onChange={(event) => setFilters((current) => ({ ...current, minRr: event.target.value }))}><option>{'>= 1.5R'}</option><option>{'>= 2R'}</option><option>{'>= 3R'}</option></select></label>
            <label className="field"><span>Risk Score</span><select value={filters.riskScore} onChange={(event) => setFilters((current) => ({ ...current, riskScore: event.target.value }))}><option>{'<= 35'}</option><option>{'<= 50'}</option><option>{'<= 65'}</option></select></label>
            <label className="field"><span>Holding Window</span><select value={filters.holdingWindow} onChange={(event) => setFilters((current) => ({ ...current, holdingWindow: event.target.value }))}><option>2-5 sessions</option><option>2-10 sessions</option><option>1-4 weeks</option></select></label>
            <label className="field"><span>Fundamentals</span><select value={filters.fundamentals} onChange={(event) => setFilters((current) => ({ ...current, fundamentals: event.target.value }))}><option>Positive or neutral</option><option>Strong only</option><option>Ignore</option></select></label>
          </div>
        )}
        <div className="quick-pick-list">
          <select value={displayLimit} onChange={(event) => setDisplayLimit(Number(event.target.value))}><option value={10}>Top 10</option><option value={25}>Top 25</option></select>
          {visibleSwingItems.slice(0, 12).map((stock: any) => {
            const symbol = symbolOf(stock);
            return (
              <button key={symbol} className="choice-card" onClick={() => addToMonitor(stock)}>
                <Pin size={14} /> {symbol}
              </button>
            );
          })}
        </div>
        <StockGrid items={visibleSwingItems} loading={loading && !visibleSwingItems.length} />
      </TerminalPanel>
    </main>
  );
}
