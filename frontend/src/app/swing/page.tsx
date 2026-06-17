"use client";
import React, { useMemo, useState } from 'react';
import { useSelector } from 'react-redux';
import { CalendarClock, Pin, LineChart, Play, ShieldCheck, Target } from 'lucide-react';
import StockGrid from '@/components/molecules/LazyStockGrid';
import { RootState } from '@/state/store';
import { getActiveScans, getLatestScanWithResults, getV20Quote, sendTelegramStockAlert, startScan } from '@/lib/api';
import { useDispatch } from 'react-redux';
import { setTopStocks } from '@/state/dashboardSlice';
import { DataTable, MetricTile, PageHero, TerminalPanel, Toolbar } from '@/components/terminal/TerminalPrimitives';
import { useToast } from '@/components/layout/ToastProvider';

export default function SwingPage() {
  const dispatch = useDispatch();
  const toast = useToast();
  const topStocks = useSelector((state: RootState) => state.dashboard.topStocks);
  const savedSettings = useSelector((state: RootState) => state.settings.data);
  const [query, setQuery] = useState('');
  const [customSymbols, setCustomSymbols] = useState('RELIANCE.NS, TCS.NS');
  const [loading, setLoading] = useState(false);
  const [displayLimit, setDisplayLimit] = useState(10);
  const [activeScans, setActiveScans] = useState<any[]>([]);
  const [selectedMonitor, setSelectedMonitor] = useState<any[]>([]);
  const [telegramAlerts, setTelegramAlerts] = useState(false);
  const alertedSymbols = React.useRef<Set<string>>(new Set());
  const topStocksRef = React.useRef<any[]>([]);
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
      try {
        const data = await getLatestScanWithResults({ scanMode: 'swing-custom', actionableOnly: false, source: 'filtered' });
        dispatch(setTopStocks(data.rows));
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
        const swingRows = rows.filter((scan: any) => /swing/i.test(`${scan.scan_type} ${scan.payload?.scan_mode}`));
        setActiveScans(swingRows);
        setLoading(swingRows.length > 0);
      } catch {
        setActiveScans([]);
      }
    }
    loadActiveScans();
    const timer = window.setInterval(loadActiveScans, 1000);
    return () => window.clearInterval(timer);
  }, []);
  const source = topStocks;
  const swingItems = useMemo(() => source.filter((item: any) => `${item.symbol} ${item.stock} ${item.sector}`.toLowerCase().includes(query.toLowerCase())), [source, query]);
  const visibleSwingItems = useMemo(() => swingItems.slice(0, displayLimit), [swingItems, displayLimit]);
  const visibleQuoteSymbols = useMemo(() => visibleSwingItems.slice(0, Math.min(displayLimit, 25)).map((stock: any) => stock.symbol || stock.stock).filter(Boolean), [visibleSwingItems, displayLimit]);
  const visibleQuoteSymbolsKey = visibleQuoteSymbols.join('|');
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

  function addToMonitor(stock: any) {
    const symbol = symbolOf(stock);
    if (!symbol) return;
    setSelectedMonitor((current) => {
      const next = current.some((item) => symbolOf(item) === symbol) ? current : [stock, ...current];
      window.localStorage.setItem(monitorStorageKey, JSON.stringify(next.map(symbolOf).filter(Boolean)));
      return next;
    });
    toast?.push(`${symbol} added to swing monitor`, 'success');
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
    const symbols = customSymbols.split(/[\s,]+/).map((symbol) => {
      const upper = symbol.trim().toUpperCase();
      return upper && !upper.includes('.') ? `${upper}.NS` : upper;
    }).filter(Boolean);
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

      <div className="metric-grid">
        <MetricTile label="Trend Aligned" value={trendAligned} detail="from multi-timeframe analysis" icon={LineChart} tone={trendAligned ? 'good' : 'warn'} />
        <MetricTile label="Risk Validated" value={riskValidated} detail="from risk model" icon={ShieldCheck} tone={riskValidated ? 'good' : 'warn'} />
        <MetricTile label="Targets Ready" value={targetsReady} detail="from target engine" icon={Target} tone={targetsReady ? 'good' : 'warn'} />
        <MetricTile label="Review Cadence" value="Daily" detail="from swing settings" icon={CalendarClock} tone="info" />
      </div>

      <TerminalPanel eyebrow="Custom Swing Scan" title="Selected Stocks Scanner">
        <div className="scan-entry-grid">
          <label className="field field--wide">
            <span>Stocks To Scan</span>
            <textarea value={customSymbols} onChange={(event) => setCustomSymbols(event.target.value)} placeholder="Enter live symbols separated by commas" rows={3} />
          </label>
          <label className="field">
            <span>Stop Loss Method</span>
            <select value={filters.stopMethod} onChange={(event) => setFilters((current) => ({ ...current, stopMethod: event.target.value }))}><option>Swing low / resistance invalidation</option><option>1.5x ATR</option><option>20 EMA close invalidation</option></select>
          </label>
          <label className="field">
            <span>Target Plan</span>
            <select value={filters.targetPlan} onChange={(event) => setFilters((current) => ({ ...current, targetPlan: event.target.value }))}><option>T1 1R / T2 2R</option><option>T1 resistance / T2 measured move</option><option>T1 1.5R / T2 3R</option></select>
          </label>
          <div className="field field--actions">
            <span>Action</span>
            <button className="btn-primary" onClick={handleRunSwingScan}><Play size={15} /> {loading ? 'Start Another' : 'Run Swing Scan'}</button>
          </div>
        </div>
      </TerminalPanel>

      <TerminalPanel eyebrow="Selected Monitor" title="Pinned Swing Watch">
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
        {!selectedMonitor.length && <p className="small">Select swing candidates to monitor stop loss and target approach.</p>}
      </TerminalPanel>

      <TerminalPanel eyebrow="Dual-Panel Scanner" title="Latest Swing Custom Filtered Stocks">
        <Toolbar search={query} setSearch={setQuery} tabs={['All', 'Breakout', 'Pullback', 'High R:R']} activeTab="All" onTabChange={() => {}} />
        <div className="form-grid">
          <label className="field"><span>Trend Filter</span><select value={filters.trend} onChange={(event) => setFilters((current) => ({ ...current, trend: event.target.value }))}><option>Uptrend or base breakout</option><option>Pullback to support</option><option>RS outperformer</option></select></label>
          <label className="field"><span>Support Distance</span><select value={filters.supportDistance} onChange={(event) => setFilters((current) => ({ ...current, supportDistance: event.target.value }))}><option>{'<= 2%'}</option><option>{'<= 3%'}</option><option>{'<= 5%'}</option></select></label>
          <label className="field"><span>Minimum R:R</span><select value={filters.minRr} onChange={(event) => setFilters((current) => ({ ...current, minRr: event.target.value }))}><option>{'>= 1.5R'}</option><option>{'>= 2R'}</option><option>{'>= 3R'}</option></select></label>
          <label className="field"><span>Risk Score</span><select value={filters.riskScore} onChange={(event) => setFilters((current) => ({ ...current, riskScore: event.target.value }))}><option>{'<= 35'}</option><option>{'<= 50'}</option><option>{'<= 65'}</option></select></label>
          <label className="field"><span>Holding Window</span><select value={filters.holdingWindow} onChange={(event) => setFilters((current) => ({ ...current, holdingWindow: event.target.value }))}><option>2-5 sessions</option><option>2-10 sessions</option><option>1-4 weeks</option></select></label>
          <label className="field"><span>Fundamentals</span><select value={filters.fundamentals} onChange={(event) => setFilters((current) => ({ ...current, fundamentals: event.target.value }))}><option>Positive or neutral</option><option>Strong only</option><option>Ignore</option></select></label>
        </div>
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
