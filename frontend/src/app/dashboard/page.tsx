"use client";
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import Link from 'next/link';
import { Bell, Filter, Globe2, Grid2X2, List, Plus, Search } from 'lucide-react';
import {
  addV20WatchlistItem,
  createV20Alert,
  getV20Dashboard,
  getV20Quote,
  localStockSearch,
  normalizeStockRow,
  saveV20Filter,
  searchStocks,
  sendTelegramStockAlert,
  type StockSearchResult,
} from '@/lib/api';
import { updateProgress } from '@/state/scanSlice';
import { setTopStocks } from '@/state/dashboardSlice';
import { RootState } from '@/state/store';
import { useRealtime } from '@/hooks/useRealtime';
import { useToast } from '@/components/layout/ToastProvider';
import StockGrid from '@/components/molecules/LazyStockGrid';
import { TerminalPanel } from '@/components/terminal/TerminalPrimitives';
import { addStocksToLiveMonitor, LIVE_MONITOR_EVENT, normalizeMonitorSymbol, readLiveMonitorRows, writeLiveMonitorRows } from '@/lib/liveMonitor';
import { GROWW_EVENT, readGrowwResults } from '@/lib/growwIntraday';
import { hydrateRowsWithMasterAnalysis } from '@/lib/unifiedAnalysis';

type SortMode = 'Profitability' | 'Growth' | 'Value' | 'Momentum' | 'AI Score';
import { playWatchlistAlertTone } from '@/lib/watchlistAlerts';

type MonitorRow = {
  symbol: string;
  live_price?: number;
  entry_price?: number;
  stop_loss?: number;
  target1?: number;
  target2?: number;
  telegram: boolean;
  status?: string;
  last_updated?: string;
  telegram_status?: string;
  custom_price_alert?: number;
  prev_price?: number;
};

type MemoizedMonitorRowProps = {
  row: MonitorRow;
  status: { label: string; tone: string; alertKey: string };
  onUpdate: (symbol: string, patch: Partial<MonitorRow>) => void;
  onRemove: (symbol: string) => void;
  onSave: (row: MonitorRow) => void;
};

const MemoizedMonitorRow = React.memo(function MemoizedMonitorRow({
  row,
  status,
  onUpdate,
  onRemove,
  onSave,
}: MemoizedMonitorRowProps) {
  const formatPrice = (value: unknown) => {
    const numeric = Number(value);
    const rounded = Number.isFinite(numeric) ? Math.round(numeric * 100) / 100 : undefined;
    return rounded === undefined ? '' : rounded.toFixed(2);
  };

  return (
    <div className="live-monitor-row">
      <div>
        <strong>{row.symbol}</strong>
        <small>{row.last_updated ? `Updated ${row.last_updated}` : row.status || 'Waiting for quote'}</small>
      </div>
      <label>
        <span>LTP</span>
        <input value={formatPrice(row.live_price)} readOnly />
      </label>
      <label>
        <span>Entry</span>
        <input
          type="number"
          value={row.entry_price ?? ''}
          onChange={(event) => onUpdate(row.symbol, { entry_price: Number(event.target.value) || undefined })}
        />
      </label>
      <label>
        <span>Stoploss</span>
        <input
          type="number"
          value={row.stop_loss ?? ''}
          onChange={(event) => onUpdate(row.symbol, { stop_loss: Number(event.target.value) || undefined })}
        />
      </label>
      <label>
        <span>Target 1</span>
        <input
          type="number"
          value={row.target1 ?? ''}
          onChange={(event) => onUpdate(row.symbol, { target1: Number(event.target.value) || undefined })}
        />
      </label>
      <label>
        <span>Target 2</span>
        <input
          type="number"
          value={row.target2 ?? ''}
          onChange={(event) => onUpdate(row.symbol, { target2: Number(event.target.value) || undefined })}
        />
      </label>
      <label>
        <span>Alert Price</span>
        <input
          type="number"
          value={row.custom_price_alert ?? ''}
          onChange={(event) => onUpdate(row.symbol, { custom_price_alert: Number(event.target.value) || undefined })}
        />
      </label>
      <label className="live-monitor-toggle">
        <span>Telegram</span>
        <input
          type="checkbox"
          checked={row.telegram}
          onChange={(event) => onUpdate(row.symbol, { telegram: event.target.checked })}
        />
      </label>
      <span className={`status-badge ${status.tone}`}>{status.label}</span>
      {row.telegram_status && (
        <small className={/failed|missing|error|invalid|forbidden|unauthorized/i.test(row.telegram_status) ? 'status-bad' : 'status-good'}>
          {row.telegram_status}
        </small>
      )}
      <button className="btn-secondary" type="button" onClick={() => onSave(row)}>
        Save
      </button>
      <button className="icon-button" type="button" title="Remove monitor" onClick={() => onRemove(row.symbol)}>
        ×
      </button>
    </div>
  );
});

export default function DashboardPage() {
  const dispatch = useDispatch();
  const toast = useToast();
  const topStocks = useSelector((state: RootState) => state.dashboard.topStocks);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [sortMode, setSortMode] = useState<SortMode>('Profitability');
  const [sectorFilter, setSectorFilter] = useState('All');
  const [ratingFilter, setRatingFilter] = useState('All');
  const [minScore, setMinScore] = useState(0);
  const [displayLimit, setDisplayLimit] = useState(10);
  const [dashboardData, setDashboardData] = useState<any>(null);
  const [error, setError] = useState('');
  const [monitorInput, setMonitorInput] = useState('');
  const [monitorRows, setMonitorRows] = useState<MonitorRow[]>([]);
  const [monitorSuggestions, setMonitorSuggestions] = useState<StockSearchResult[]>([]);
  const [monitorSuggestionsLoading, setMonitorSuggestionsLoading] = useState(false);
  const [showMonitorSuggestions, setShowMonitorSuggestions] = useState(false);
  const [growwRows, setGrowwRows] = useState<any[]>([]);
  const [growwUpdatedAt, setGrowwUpdatedAt] = useState('');
  const sentAlertKeys = React.useRef<Set<string>>(new Set());
  const failedAlertKeys = React.useRef<Set<string>>(new Set());
  const monitorRowsRef = React.useRef<MonitorRow[]>([]);
  const dashboardLoadingRef = React.useRef(false);
  const dashboardSuccessRef = React.useRef(false);
  const dashboardFailuresRef = React.useRef(0);
  const monitorRefreshingRef = React.useRef(false);
  const monitorStorageReadyRef = React.useRef(false);
  const monitorHydratingRef = React.useRef(false);
  const topStocksRef = React.useRef<any[]>([]);
  const visibleQuotesRefreshingRef = React.useRef(false);

  function normalizeSymbolToken(value: string) {
    return normalizeMonitorSymbol(value);
  }

  function parseSymbols(value: string) {
    return Array.from(new Set(value.split(/[\s,;]+/).map(normalizeSymbolToken).filter(Boolean)));
  }

  function monitorDisplaySymbol(stock: StockSearchResult) {
    return stock.exchange === 'BSE'
      ? (stock.bse_symbol || stock.symbol.replace(/\.BO$/, ''))
      : (stock.nse_symbol || stock.symbol.replace(/\.NS$/, ''));
  }

  function roundPrice(value: unknown) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? Math.round(numeric * 100) / 100 : undefined;
  }

  function formatPrice(value: unknown) {
    const rounded = roundPrice(value);
    return rounded === undefined ? '' : rounded.toFixed(2);
  }

  function clearMonitorAlertMemory(symbol: string) {
    [sentAlertKeys.current, failedAlertKeys.current].forEach((store) => {
      Array.from(store).forEach((key) => {
        if (key.startsWith(`${symbol}-`)) store.delete(key);
      });
    });
  }

  useEffect(() => {
    async function load(silent = false) {
      if (dashboardLoadingRef.current) return;
      try {
        dashboardLoadingRef.current = true;
        const data = await getV20Dashboard();
        const rows = (data.top_stocks || []).map(normalizeStockRow);
        dispatch(setTopStocks(rows));
        setDashboardData(data);
        dashboardSuccessRef.current = true;
        dashboardFailuresRef.current = 0;
        setError('');
      } catch (err) {
        dashboardFailuresRef.current += 1;
        if (!dashboardSuccessRef.current && !topStocksRef.current.length) {
          dispatch(setTopStocks([]));
          setError('Unable to load Version 20 dashboard API');
          if (!silent) toast?.push('Unable to load live dashboard data from backend', 'error');
        } else {
          setError('');
          if (!silent && dashboardFailuresRef.current === 3) {
            toast?.push('Dashboard refresh is delayed; showing last live data', 'warning');
          }
        }
      } finally {
        setLoading(false);
        dashboardLoadingRef.current = false;
      }
    }
    load();
    const timer = window.setInterval(() => load(true), 1000);
    return () => window.clearInterval(timer);
  }, [dispatch, toast]);

  useEffect(() => {
    try {
      const saved = readLiveMonitorRows();
      if (Array.isArray(saved)) {
        monitorHydratingRef.current = true;
        monitorRowsRef.current = saved;
        setMonitorRows(saved);
      }
    } catch {
      window.localStorage.removeItem('dashboard-live-monitor');
    } finally {
      monitorStorageReadyRef.current = true;
    }
    function handleExternalMonitorUpdate(event: Event) {
      const rows = (event as CustomEvent).detail?.rows || readLiveMonitorRows();
      if (!Array.isArray(rows)) return;
      monitorRowsRef.current = rows;
      setMonitorRows(rows);
    }
    window.addEventListener(LIVE_MONITOR_EVENT, handleExternalMonitorUpdate);
    return () => window.removeEventListener(LIVE_MONITOR_EVENT, handleExternalMonitorUpdate);
  }, []);

  useEffect(() => {
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

  useEffect(() => {
    if (!monitorStorageReadyRef.current) return;
    if (monitorHydratingRef.current) {
      monitorHydratingRef.current = false;
      monitorRowsRef.current = monitorRows;
      return;
    }
    writeLiveMonitorRows(monitorRows);
    monitorRowsRef.current = monitorRows;
  }, [monitorRows]);

  function monitorStatus(row: MonitorRow) {
    const live = Number(row.live_price || 0);
    const stop = Number(row.stop_loss || 0);
    const target1 = Number(row.target1 || 0);
    const target2 = Number(row.target2 || 0);
    const alertPrice = Number(row.custom_price_alert || 0);
    const prev = Number(row.prev_price || 0);
    
    if (!live) return { label: 'Waiting for quote', tone: 'status-warn', alertKey: '' };
    
    // Check custom price alert crossover
    if (alertPrice > 0 && prev > 0) {
      const crossedAbove = prev < alertPrice && live >= alertPrice;
      const crossedBelow = prev > alertPrice && live <= alertPrice;
      if (crossedAbove || crossedBelow) {
        return { label: `Alert price reached: ${live}`, tone: 'status-good', alertKey: `price-alert-${alertPrice}` };
      }
    }
    
    if (stop && live <= stop) return { label: 'Stoploss hit', tone: 'status-bad', alertKey: 'stop-hit' };
    if (target2 && live >= target2) return { label: 'Target 2 hit', tone: 'status-good', alertKey: 'target2-hit' };
    if (target1 && live >= target1) return { label: 'Target 1 hit', tone: 'status-good', alertKey: 'target1-hit' };
    if (stop && Math.abs((live - stop) / live) <= 0.0025) return { label: 'Near stoploss', tone: 'status-bad', alertKey: 'near-stop' };
    if (target1 && Math.abs((target1 - live) / live) <= 0.005) return { label: 'Near target 1', tone: 'status-good', alertKey: 'near-target1' };
    if (target2 && Math.abs((target2 - live) / live) <= 0.005) return { label: 'Near target 2', tone: 'status-good', alertKey: 'near-target2' };
    return { label: 'Monitoring', tone: 'status-warn', alertKey: '' };
  }

  async function processMonitorTelegramAlerts(rows: MonitorRow[]) {
    rows.forEach(async (row) => {
      const status = monitorStatus(row);
      if (!status.alertKey) return;
      const key = `${row.symbol}-${status.alertKey}`;
      if (sentAlertKeys.current.has(key) || failedAlertKeys.current.has(key)) return;
      
      // Mark as processed immediately to prevent duplicate loops
      sentAlertKeys.current.add(key);

      // Play local sound chime
      playWatchlistAlertTone('high', 'BUY');

      // Toast notification in layout
      toast?.push(`Alert: ${row.symbol} - ${status.label}`, 'success');

      // Trigger browser desktop OS push notifications
      if (typeof window !== 'undefined' && 'Notification' in window) {
        if (window.Notification.permission === 'granted') {
          new window.Notification(`Stock Monitor Alert: ${row.symbol}`, {
            body: `${row.symbol} - ${status.label}`,
            tag: key
          });
        } else if (window.Notification.permission === 'default') {
          window.Notification.requestPermission().then((permission) => {
            if (permission === 'granted') {
              new window.Notification(`Stock Monitor Alert: ${row.symbol}`, {
                body: `${row.symbol} - ${status.label}`,
                tag: key
              });
            }
          });
        }
      }

      // Send Telegram alert if telegram checked
      if (row.telegram) {
        try {
          await sendTelegramStockAlert({ ...row, status: status.label, telegram_category: 'Intraday' });
          setMonitorRows((current) => {
            const next = current.map((item) => item.symbol === row.symbol ? { ...item, telegram_status: `Telegram sent: ${status.label}` } : item);
            monitorRowsRef.current = next;
            return next;
          });
          toast?.push(`Telegram alert sent: ${row.symbol} ${status.label}`, 'success');
        } catch (error: any) {
          const message = error?.message || 'Telegram failed. Check Telegram settings.';
          failedAlertKeys.current.add(key);
          setMonitorRows((current) => {
            const next = current.map((item) => item.symbol === row.symbol ? { ...item, telegram_status: message } : item);
            monitorRowsRef.current = next;
            return next;
          });
          toast?.push(`Telegram alert failed for ${row.symbol}: ${message}`, 'error');
        }
      }
    });
  }

  async function refreshMonitorQuotes(rows = monitorRowsRef.current) {
    if (!rows.length || monitorRefreshingRef.current) return;
    monitorRefreshingRef.current = true;
    try {
      const quoteUpdates = await Promise.all(rows.map(async (row) => {
        try {
          const payload = await getV20Quote(row.symbol);
          const quote = payload?.quote || {};
          const live = Number(quote.current_price ?? quote.regularMarketPrice ?? quote.price ?? quote.last_close ?? row.live_price ?? 0);
          return {
            symbol: row.symbol,
            live_price: Number.isFinite(live) && live > 0 ? roundPrice(live) : undefined,
            last_updated: new Date().toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true }),
            status: undefined,
          };
        } catch {
          return { symbol: row.symbol, status: 'Quote unavailable' };
        }
      }));
      const updatesBySymbol = new Map(quoteUpdates.map((item) => [item.symbol, item]));
      const merged = monitorRowsRef.current.map((row) => {
        const update = updatesBySymbol.get(row.symbol);
        if (!update) return row;
        return {
          ...row,
          prev_price: row.live_price,
          live_price: update.live_price ?? row.live_price,
          last_updated: update.last_updated ?? row.last_updated,
          status: update.status ?? row.status,
        };
      });
      monitorRowsRef.current = merged;
      setMonitorRows(merged);
      await processMonitorTelegramAlerts(merged);
    } finally {
      monitorRefreshingRef.current = false;
    }
  }

  useEffect(() => {
    if (!monitorRows.length) return;
    refreshMonitorQuotes(monitorRowsRef.current);
    const timer = window.setInterval(() => refreshMonitorQuotes(monitorRowsRef.current), 1000);
    return () => window.clearInterval(timer);
  }, [monitorRows.length]);

  useRealtime((msg) => {
    if (msg?.type === 'scan-result') {
      void hydrateRowsWithMasterAnalysis(msg.payload?.results || [], 30).then((rows) => dispatch(setTopStocks(rows)));
    }
    if (msg?.type === 'scan.update') dispatch(updateProgress({ [msg.payload?.scan_id]: msg.payload }));
  });

  const stocks = topStocks;
  const sectors = useMemo(() => Array.from(new Set(stocks.map((stock: any) => stock.sector).filter(Boolean))).sort(), [stocks]);
  const filtered = useMemo(() => {
    const sortKeyMap: Record<SortMode, string> = {
      Profitability: 'profitability_score',
      Growth: 'growth_score',
      Value: 'value_score',
      Momentum: 'momentum_score',
      'AI Score': 'final_ai_score',
    };
    const rows = stocks.filter((stock: any) => {
      const haystack = `${stock.symbol} ${stock.stock} ${stock.sector} ${stock.action}`.toLowerCase();
      const matchesQuery = haystack.includes(query.toLowerCase());
      const matchesSector = sectorFilter === 'All' || stock.sector === sectorFilter;
      const action = String(stock.action || stock.ai_rating || '').toUpperCase();
      const matchesRating = ratingFilter === 'All' || action === ratingFilter.toUpperCase();
      const score = Number(stock.final_ai_score ?? stock.profitability_score ?? stock.confidence_pct ?? 0);
      return matchesQuery && matchesSector && matchesRating && score >= minScore;
    });
    const sortKey = sortKeyMap[sortMode];
    return rows.sort((a: any, b: any) => Number(b[sortKey] ?? b.profitability_score ?? 0) - Number(a[sortKey] ?? a.profitability_score ?? 0));
  }, [stocks, query, sectorFilter, ratingFilter, minScore, sortMode]);

  const visibleFiltered = useMemo(() => filtered.slice(0, displayLimit), [filtered, displayLimit]);
  const visibleQuoteSymbols = useMemo(
    () => visibleFiltered
      .slice(0, Math.min(displayLimit, 25))
      .map((stock: any) => stock.symbol || stock.stock)
      .filter(Boolean),
    [visibleFiltered, displayLimit],
  );
  const visibleQuoteSymbolsKey = visibleQuoteSymbols.join('|');

  useEffect(() => {
    topStocksRef.current = topStocks;
  }, [topStocks]);

  useEffect(() => {
    const activeToken = monitorInput.split(',').pop()?.trim() || '';
    if (!showMonitorSuggestions || activeToken.length < 2) {
      setMonitorSuggestions([]);
      setMonitorSuggestionsLoading(false);
      return;
    }

    let cancelled = false;
    const localResults = localStockSearch(activeToken, 8);
    setMonitorSuggestions(localResults);
    setMonitorSuggestionsLoading(true);
    searchStocks(activeToken, 8)
      .then((payload) => {
        if (cancelled) return;
        const merged = [...(payload.results || [])];
        for (const fallback of localResults) {
          if (!merged.some((stock) => stock.symbol === fallback.symbol)) merged.push(fallback);
        }
        setMonitorSuggestions(merged.slice(0, 8));
      })
      .catch(() => {
        if (!cancelled) setMonitorSuggestions(localResults);
      })
      .finally(() => {
        if (!cancelled) setMonitorSuggestionsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [monitorInput, showMonitorSuggestions]);



  async function handleSaveFilter(name: string, filters: Record<string, unknown>) {
    try {
      await saveV20Filter(name, filters);
      toast?.push(`${name} saved`, 'success');
    } catch {
      toast?.push('Unable to save filter', 'error');
    }
  }

  async function addMonitorSymbols() {
    const symbols = parseSymbols(monitorInput);
    if (!symbols.length) {
      toast?.push('Enter at least one stock symbol', 'warning');
      return;
    }
    const additions = symbols.map((symbol) => ({
      symbol,
      telegram: false,
      entry_price: undefined,
      stop_loss: undefined,
      target1: undefined,
      target2: undefined,
      custom_price_alert: undefined,
    }));
    const result = addStocksToLiveMonitor(additions, 'dashboard');
    monitorRowsRef.current = result.rows;
    setMonitorRows(result.rows);
    setMonitorInput(symbols.join(', '));
    toast?.push(`${result.added || symbols.length} symbol(s) added to live monitor`, 'success');
  }

  function selectMonitorSuggestion(stock: StockSearchResult) {
    const parts = monitorInput.split(',');
    parts[parts.length - 1] = ` ${monitorDisplaySymbol(stock)}`;
    setMonitorInput(parts.join(',').trimStart());
    setMonitorSuggestions([]);
    setShowMonitorSuggestions(false);
  }

  const updateMonitor = useCallback((symbol: string, patch: Partial<MonitorRow>) => {
    if ('entry_price' in patch || 'stop_loss' in patch || 'target1' in patch || 'target2' in patch || 'telegram' in patch || 'custom_price_alert' in patch) {
      clearMonitorAlertMemory(symbol);
      patch.telegram_status = '';
    }
    setMonitorRows((current) => {
      const next = current.map((row) => row.symbol === symbol ? { ...row, ...patch } : row);
      monitorRowsRef.current = next;
      return next;
    });
  }, []);

  const removeMonitor = useCallback((symbol: string) => {
    clearMonitorAlertMemory(symbol);
    setMonitorRows((current) => {
      const next = current.filter((row) => row.symbol !== symbol);
      monitorRowsRef.current = next;
      return next;
    });
  }, []);

  const saveMonitorAlert = useCallback(async (row: MonitorRow) => {
    try {
      if (row.target1) await createV20Alert({ symbol: row.symbol, alert_type: 'target', condition: 'above', threshold: Number(row.target1) });
      if (row.stop_loss) await createV20Alert({ symbol: row.symbol, alert_type: 'stoploss', condition: 'below', threshold: Number(row.stop_loss) });
      if (row.custom_price_alert) await createV20Alert({ symbol: row.symbol, alert_type: 'custom_price', condition: 'above', threshold: Number(row.custom_price_alert) });
      await addV20WatchlistItem(row.symbol);
      toast?.push(`${row.symbol} alert levels saved and added to watchlist`, 'success');
    } catch {
      toast?.push(`Unable to save alert levels for ${row.symbol}`, 'error');
    }
  }, [toast]);

  return (
    <main className="reference-dashboard">
      <div className="filter-strip">
        <label><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search live results" /></label>
        <label><Globe2 size={16} /><select value={ratingFilter} onChange={(event) => setRatingFilter(event.target.value)}><option>All</option><option>Strong Buy</option><option>Buy</option><option>Watch</option><option>Hold</option><option>Avoid</option></select></label>
        <label>Sector <select value={sectorFilter} onChange={(event) => setSectorFilter(event.target.value)}><option>All</option>{sectors.map((sector) => <option key={sector}>{sector}</option>)}</select></label>
        <label>Min Score <select value={minScore} onChange={(event) => setMinScore(Number(event.target.value))}><option value={0}>All Scores</option><option value={60}>60+</option><option value={75}>75+</option><option value={85}>85+</option></select></label>
        <label>Show <select value={displayLimit} onChange={(event) => setDisplayLimit(Number(event.target.value))}><option value={8}>8</option><option value={15}>15</option><option value={25}>25</option><option value={50}>50</option></select></label>
        <button type="button" onClick={() => { setSectorFilter('All'); setRatingFilter('All'); setMinScore(0); setSortMode('Profitability'); }}><Filter size={15} /> Reset</button>
      </div>
      {error && <div className="status-badge status-bad">{error}</div>}
      {!loading && dashboardData?.data_status === 'unavailable' && (
        <div className="status-badge status-warn">{dashboardData.message || 'Live market data unavailable. Run a scan or configure a provider.'}</div>
      )}

      <section className="dashboard-shell-grid">
        <div className="dashboard-main-column">
          <TerminalPanel
            className="live-stock-monitor-panel"
            title="Live Stock Monitor"
            actions={<button className="link-button" type="button" onClick={() => refreshMonitorQuotes()}><Bell size={14} /> Refresh</button>}
          >
            <div className="live-monitor-entry">
              <div className="live-monitor-search">
                <label className="field">
                  <span>Symbols</span>
                  <input
                    value={monitorInput}
                    onFocus={() => setShowMonitorSuggestions(true)}
                    onBlur={() => window.setTimeout(() => {
                      setShowMonitorSuggestions(false);
                      setMonitorInput(parseSymbols(monitorInput).join(', '));
                    }, 140)}
                    onChange={(event) => {
                      setMonitorInput(event.target.value);
                      setShowMonitorSuggestions(true);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') addMonitorSymbols();
                      if (event.key === 'Escape') setShowMonitorSuggestions(false);
                    }}
                    placeholder="RELIANCE, TCS, INFY"
                  />
                </label>
                {showMonitorSuggestions && (monitorSuggestionsLoading || monitorSuggestions.length > 0) && (
                  <div className="watchlist-stock-suggestions live-monitor-suggestions">
                    {monitorSuggestionsLoading && !monitorSuggestions.length && (
                      <div className="watchlist-stock-suggestion is-muted">Searching...</div>
                    )}
                    {monitorSuggestions.map((stock) => (
                      <button
                        className="watchlist-stock-suggestion"
                        key={`${stock.exchange}-${stock.symbol}`}
                        type="button"
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => selectMonitorSuggestion(stock)}
                      >
                        <span>
                          <strong>{monitorDisplaySymbol(stock)}</strong>
                          <small>{stock.exchange}</small>
                        </span>
                        <em>{stock.name}</em>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <button className="btn-primary live-monitor-add" type="button" onClick={addMonitorSymbols}><Plus size={14} /> Add</button>
            </div>
            <div className="live-monitor-list">
              {monitorRows.length ? monitorRows.map((row) => (
                <MemoizedMonitorRow
                  key={row.symbol}
                  row={row}
                  status={monitorStatus(row)}
                  onUpdate={updateMonitor}
                  onRemove={removeMonitor}
                  onSave={saveMonitorAlert}
                />
              )) : <div className="empty-inline">Add stocks to monitor live price, target, stoploss, and Telegram alerts.</div>}
            </div>
          </TerminalPanel>

          <TerminalPanel eyebrow="Third Party Source" title="Groww Intraday Filtered Stocks" actions={<Link className="link-button" href="/groww-intraday">Configure Auto</Link>}>
            <p className="small">
              {growwUpdatedAt ? `Last Groww analysis: ${new Date(growwUpdatedAt).toLocaleString('en-IN')}` : 'No Groww auto analysis yet. Enable it from Groww Source.'}
            </p>
            <StockGrid items={growwRows.slice(0, 20)} loading={false} pageSize={10} />
          </TerminalPanel>

          <TerminalPanel eyebrow="" title="Top Profitable Stocks">
            <div className="profit-tabs">
              {(['Profitability', 'Growth', 'Value', 'Momentum', 'AI Score'] as SortMode[]).map((label) => (
                <button key={label} className={sortMode === label ? 'active' : ''} type="button" onClick={() => setSortMode(label)}>{label}</button>
              ))}
              <div className="profit-tabs__right">
                <select value={sortMode} onChange={(event) => setSortMode(event.target.value as SortMode)}>
                  <option value="Profitability">Sort by: Profitability</option>
                  <option value="Growth">Sort by: Growth</option>
                  <option value="Value">Sort by: Value</option>
                  <option value="Momentum">Sort by: Momentum</option>
                  <option value="AI Score">Sort by: AI Score</option>
                </select>
                <button className="icon-button" type="button" title="Save grid filter" onClick={() => handleSaveFilter('Grid View', { displayLimit })}><Grid2X2 size={15} /></button>
                <button className="icon-button" type="button" title="Save current filter" onClick={() => handleSaveFilter('Current Dashboard Filter', { sectorFilter, ratingFilter, minScore, sortMode, displayLimit })}><List size={15} /></button>
              </div>
            </div>
            <StockGrid items={visibleFiltered} loading={loading} pageSize={8} />
          </TerminalPanel>
        </div>
      </section>
    </main>
  );
}
