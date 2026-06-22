"use client";
import React, { useEffect, useMemo, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import Link from 'next/link';
import { BarChart3, Bell, Filter, Globe2, Grid2X2, List, Plus, Search, Star, TrendingUp } from 'lucide-react';
import { addV20WatchlistItem, createV20Alert, createV20PaperTrade, getActiveScans, getV20Dashboard, getV20Quote, normalizeStockRow, saveV20Filter, sendTelegramStockAlert } from '@/lib/api';
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
type KpiKey = 'total' | 'profitability' | 'strongBuy' | 'sentiment' | 'intraday' | 'swing' | 'longterm';
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
};

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
  const [activeKpi, setActiveKpi] = useState<KpiKey>('total');
  const [activeScans, setActiveScans] = useState<any[]>([]);
  const [dashboardData, setDashboardData] = useState<any>(null);
  const [error, setError] = useState('');
  const [showAllNews, setShowAllNews] = useState(false);
  const [monitorInput, setMonitorInput] = useState('');
  const [monitorRows, setMonitorRows] = useState<MonitorRow[]>([]);
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
        const [data, active] = await Promise.all([getV20Dashboard(), getActiveScans()]);
        const rows = await hydrateRowsWithMasterAnalysis((data.top_stocks || []).map(normalizeStockRow), 30);
        dispatch(setTopStocks(rows));
        setActiveScans(active.active_scans || active.scans || []);
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
    const timer = window.setInterval(() => load(true), 3000);
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
    if (!live) return { label: 'Waiting for quote', tone: 'status-warn', alertKey: '' };
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
      if (!row.telegram) return;
      const status = monitorStatus(row);
      if (!status.alertKey) return;
      const key = `${row.symbol}-${status.alertKey}`;
      if (sentAlertKeys.current.has(key) || failedAlertKeys.current.has(key)) return;
      try {
        await sendTelegramStockAlert({ ...row, status: status.label, telegram_category: 'Intraday' });
        sentAlertKeys.current.add(key);
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
  const kpis = dashboardData?.kpis || {};
  const breadth = dashboardData?.breadth;
  const tradeAvailability = dashboardData?.trade_availability || {};
  const marketSentiment = dashboardData?.market_sentiment || {};
  const hasLiveRows = dashboardData?.data_status === 'live' && stocks.length > 0;
  const metric = (value: unknown, suffix = '') => (value === null || value === undefined || value === '' ? 'Data unavailable' : `${value}${suffix}`);
  const dashboardFreshness = dashboardData?.last_updated || dashboardData?.updated_at || dashboardData?.created_at || dashboardData?.data_updated_at || '';
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
  const sectorWidgets = dashboardData?.sector_heatmap || [];
  const topOpportunities = (dashboardData?.top_opportunities || []).map(normalizeStockRow);
  const watchlistPreview = dashboardData?.watchlist || [];
  const news = dashboardData?.news || [];
  const visibleNews = showAllNews ? news : news.slice(0, 4);
  const aiInsights = dashboardData?.ai_insights || [];

  function rowSearchText(row: any) {
    return `${row.symbol || ''} ${row.stock || ''} ${row.sector || ''} ${row.action || ''} ${row.ai_rating || ''} ${row.scan_type || ''} ${row.scan_family || ''} ${row.scanner_bucket || ''} ${row.pipeline_stage || ''} ${row.best_horizon || ''} ${row.category || ''} ${row.source_name || ''}`.toLowerCase();
  }

  function rowSymbol(row: any) {
    return row.symbol || row.stock || row.ticker || 'Symbol unavailable';
  }

  function rowScore(row: any) {
    const score = Number(row.final_ai_score ?? row.profitability_score ?? row.ml_score ?? row.ml_confidence ?? row.confidence_pct);
    return Number.isFinite(score) ? Math.round(score) : null;
  }

  function rowSignal(row: any) {
    return row.action || row.ai_rating || row.signal || row.final_decision || 'Data unavailable';
  }

  function rowReason(row: any) {
    return row.reason || row.trade_reason || row.quality_filter_reasons || row.explanation || 'Reason unavailable from backend';
  }

  const strongBuyRows = filtered.filter((row: any) => /strong\s*buy/i.test(String(row.action || row.ai_rating || row.signal || '')));
  const intradayRows = filtered.filter((row: any) => /intraday|premarket|market-open|open[-_ ]?confirmation|groww/.test(rowSearchText(row)));
  const swingRows = filtered.filter((row: any) => /swing|multi[- ]?day|positional/.test(rowSearchText(row)));
  const longTermRows = filtered.filter((row: any) => /long[- ]?term|value|dividend|quality|fundamental/.test(rowSearchText(row)));

  const kpiDetail = (() => {
    const baseMetrics = [
      { label: 'Visible rows', value: String(filtered.length) },
      { label: 'Last updated', value: dashboardFreshness ? new Date(dashboardFreshness).toLocaleString('en-IN') : 'Data unavailable' },
    ];
    if (activeKpi === 'profitability') {
      return {
        title: 'Profitability Score Detail',
        body: 'Average score, highest ranked rows, and score source from the live profitability engine.',
        href: '/scan-center',
        rows: [...filtered].sort((a: any, b: any) => Number(b.profitability_score ?? b.final_ai_score ?? 0) - Number(a.profitability_score ?? a.final_ai_score ?? 0)),
        metrics: [
          { label: 'Average', value: metric(kpis.avg_profitability_score, '/100') },
          { label: 'Rows scored', value: String(filtered.filter((row: any) => rowScore(row) !== null).length) },
          ...baseMetrics,
        ],
      };
    }
    if (activeKpi === 'strongBuy') {
      return {
        title: 'Strong Buy Detail',
        body: 'Rows currently classified as Strong Buy by the backend recommendation/scoring pipeline.',
        href: '/scan-center',
        rows: strongBuyRows,
        metrics: [
          { label: 'Strong Buy', value: metric(kpis.strong_buy_count ?? strongBuyRows.length) },
          { label: 'Share of live rows', value: stocks.length ? `${Math.round(((Number(kpis.strong_buy_count ?? strongBuyRows.length) || 0) / Math.max(stocks.length, 1)) * 100)}%` : 'Data unavailable' },
          ...baseMetrics,
        ],
      };
    }
    if (activeKpi === 'sentiment') {
      return {
        title: 'AI Market Sentiment Detail',
        body: 'Market sentiment is shown only from live breadth, trend, and scoring payloads returned by backend APIs.',
        href: '/ai-insights',
        rows: topOpportunities.length ? topOpportunities : filtered,
        metrics: [
          { label: 'Sentiment', value: kpis.market_sentiment || 'Data unavailable' },
          { label: 'Sentiment score', value: kpis.market_sentiment_score === undefined ? 'Data unavailable' : `${kpis.market_sentiment_score}/100` },
          { label: 'Advances', value: breadth ? `${breadth.advances} (${breadth.advance_pct}%)` : 'Data unavailable' },
          { label: 'Declines', value: breadth ? `${breadth.declines} (${breadth.decline_pct}%)` : 'Data unavailable' },
          { label: 'Source', value: marketSentiment.source || 'Live market data only' },
        ],
      };
    }
    if (activeKpi === 'intraday') {
      return {
        title: 'Intraday Trade-Ready Detail',
        body: 'Unique intraday candidates from intraday, premarket, open confirmation, Groww, and live scan rows.',
        href: '/intraday',
        rows: intradayRows,
        metrics: [
          { label: 'Available', value: metric(kpis.intraday_available ?? tradeAvailability.intraday?.count ?? intradayRows.length) },
          { label: 'Rows on page', value: String(intradayRows.length) },
          { label: 'Source', value: 'Intraday pipeline' },
          ...baseMetrics,
        ],
      };
    }
    if (activeKpi === 'swing') {
      return {
        title: 'Swing Trade-Ready Detail',
        body: 'Multi-day candidates from swing scanners and backend scoring, kept separate from intraday rows.',
        href: '/swing',
        rows: swingRows,
        metrics: [
          { label: 'Available', value: metric(kpis.swing_available ?? tradeAvailability.swing?.count ?? swingRows.length) },
          { label: 'Rows on page', value: String(swingRows.length) },
          { label: 'Source', value: 'Swing pipeline' },
          ...baseMetrics,
        ],
      };
    }
    if (activeKpi === 'longterm') {
      return {
        title: 'Long-Term Available Detail',
        body: 'Long-term, value, dividend, quality, and fundamental candidates from backend scoring.',
        href: '/scan-center',
        rows: longTermRows,
        metrics: [
          { label: 'Available', value: metric(kpis.longterm_available ?? tradeAvailability.longterm?.count ?? longTermRows.length) },
          { label: 'Rows on page', value: String(longTermRows.length) },
          { label: 'Source', value: 'Long-term scoring' },
          ...baseMetrics,
        ],
      };
    }
    return {
      title: 'Total Opportunities Detail',
      body: 'All live dashboard opportunities after the current search, sector, rating, and minimum score filters.',
      href: '/scan-center',
      rows: filtered.length ? filtered : topOpportunities,
      metrics: [
        { label: 'Backend total', value: metric(kpis.total_opportunities) },
        { label: 'Filtered visible', value: String(filtered.length) },
        { label: 'Active scans', value: String(activeScans.length) },
        ...baseMetrics,
      ],
    };
  })();

  const kpiCards: Array<{ key: KpiKey; className?: string; label: string; value: React.ReactNode; note: React.ReactNode; visual?: React.ReactNode }> = [
    {
      key: 'total',
      label: 'Total Opportunities',
      value: metric(kpis.total_opportunities),
      note: <small className={activeScans.length ? 'status-good' : ''}>{activeScans.length ? `${activeScans.length} active scans` : 'Live scanner results only'}</small>,
      visual: <i className="spark spark--green" />,
    },
    {
      key: 'profitability',
      className: 'reference-kpi--violet',
      label: 'Avg. Profitability Score',
      value: kpis.avg_profitability_score === undefined ? 'Data unavailable' : <>{kpis.avg_profitability_score}<em>/100</em></>,
      note: <small className={hasLiveRows ? 'status-good' : ''}>from live profitability engine</small>,
      visual: <i className="spark spark--violet" />,
    },
    {
      key: 'strongBuy',
      label: 'Strong Buy',
      value: metric(kpis.strong_buy_count),
      note: <small>{stocks.length && kpis.strong_buy_count !== undefined ? `${Math.round(((kpis.strong_buy_count || 0) / Math.max(stocks.length, 1)) * 100)}% of live results` : 'Data unavailable'}</small>,
      visual: <b className="donut" />,
    },
    {
      key: 'sentiment',
      label: 'AI Market Sentiment',
      value: kpis.market_sentiment ? <>{kpis.market_sentiment} <em>{kpis.market_sentiment_score}/100</em></> : 'Data unavailable',
      note: <small>{marketSentiment.source || 'Calculated from live market data only'}</small>,
      visual: <div className="sentiment-bar"><i style={{ width: `${Number(kpis.market_sentiment_score || 0)}%` }} /></div>,
    },
    {
      key: 'intraday',
      label: 'Intraday Trade-Ready',
      value: metric(kpis.intraday_available ?? tradeAvailability.intraday?.count),
      note: <small>unique symbols from intraday, premarket/open, Groww, and live scan rows</small>,
    },
    {
      key: 'swing',
      label: 'Swing Trade-Ready',
      value: metric(kpis.swing_available ?? tradeAvailability.swing?.count),
      note: <small>unique symbols from swing scanners and live multi-day scoring</small>,
    },
    {
      key: 'longterm',
      className: 'reference-kpi--violet',
      label: 'Long-Term Available',
      value: metric(kpis.longterm_available ?? tradeAvailability.longterm?.count),
      note: <small>unique symbols from long-term, value, dividend, quality, and live scoring</small>,
    },
  ];

  useEffect(() => {
    topStocksRef.current = topStocks;
  }, [topStocks]);

  useEffect(() => {
    if (!visibleQuoteSymbols.length) return;
    async function refreshVisibleQuotes() {
      if (visibleQuotesRefreshingRef.current) return;
      visibleQuotesRefreshingRef.current = true;
      try {
        const quotes = await Promise.all(visibleQuoteSymbols.map(async (symbol) => {
          try {
            const payload = await getV20Quote(symbol);
            const quote = payload?.quote || {};
            const live = roundPrice(quote.current_price ?? quote.regularMarketPrice ?? quote.price);
            const previous = Number(quote.previous_close || 0);
            const change = live !== undefined && previous ? roundPrice(((live - previous) / previous) * 100) : undefined;
            return { symbol, live, change };
          } catch {
            return { symbol };
          }
        }));
        const bySymbol = new Map(quotes.filter((item) => item.live !== undefined).map((item) => [item.symbol, item]));
        if (!bySymbol.size) return;
        dispatch(setTopStocks(topStocksRef.current.map((stock: any) => {
          const symbol = stock.symbol || stock.stock;
          const quote = bySymbol.get(symbol);
          return quote ? { ...stock, live_price: quote.live, current_price: quote.live, change_pct: quote.change ?? stock.change_pct, last_updated: new Date().toISOString() } : stock;
        })));
      } finally {
        visibleQuotesRefreshingRef.current = false;
      }
    }
    refreshVisibleQuotes();
    const timer = window.setInterval(refreshVisibleQuotes, 1000);
    return () => window.clearInterval(timer);
  }, [dispatch, visibleQuoteSymbolsKey]);

  async function handleSaveFilter(name: string, filters: Record<string, unknown>) {
    try {
      await saveV20Filter(name, filters);
      toast?.push(`${name} saved`, 'success');
    } catch {
      toast?.push('Unable to save filter', 'error');
    }
  }

  async function handleWatch(symbol: string) {
    try {
      await addV20WatchlistItem(symbol);
      toast?.push(`${symbol} added to watchlist`, 'success');
    } catch {
      toast?.push('Unable to update watchlist', 'error');
    }
  }

  async function handleAlert(symbol: string, score: number) {
    try {
      await createV20Alert({ symbol, alert_type: 'ai_score', condition: 'above', threshold: score });
      toast?.push(`Alert created for ${symbol}`, 'success');
    } catch {
      toast?.push('Unable to create alert', 'error');
    }
  }

  async function handlePaperTrade(symbol: string, price: number) {
    try {
      await createV20PaperTrade({ symbol, side: 'BUY', quantity: 1, entry_price: price });
      toast?.push(`Paper trade opened for ${symbol}`, 'success');
    } catch {
      toast?.push('Unable to open paper trade', 'error');
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
    }));
    const result = addStocksToLiveMonitor(additions, 'dashboard');
    monitorRowsRef.current = result.rows;
    setMonitorRows(result.rows);
    setMonitorInput(symbols.join(', '));
    toast?.push(`${result.added || symbols.length} symbol(s) added to live monitor`, 'success');
  }

  function updateMonitor(symbol: string, patch: Partial<MonitorRow>) {
    if ('entry_price' in patch || 'stop_loss' in patch || 'target1' in patch || 'target2' in patch || 'telegram' in patch) {
      clearMonitorAlertMemory(symbol);
      patch.telegram_status = '';
    }
    setMonitorRows((current) => {
      const next = current.map((row) => row.symbol === symbol ? { ...row, ...patch } : row);
      monitorRowsRef.current = next;
      return next;
    });
  }

  function removeMonitor(symbol: string) {
    clearMonitorAlertMemory(symbol);
    setMonitorRows((current) => {
      const next = current.filter((row) => row.symbol !== symbol);
      monitorRowsRef.current = next;
      return next;
    });
  }

  async function saveMonitorAlert(row: MonitorRow) {
    try {
      if (row.target1) await createV20Alert({ symbol: row.symbol, alert_type: 'target', condition: 'above', threshold: Number(row.target1) });
      if (row.stop_loss) await createV20Alert({ symbol: row.symbol, alert_type: 'stoploss', condition: 'below', threshold: Number(row.stop_loss) });
      await addV20WatchlistItem(row.symbol);
      toast?.push(`${row.symbol} alert levels saved and added to watchlist`, 'success');
    } catch {
      toast?.push(`Unable to save alert levels for ${row.symbol}`, 'error');
    }
  }

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
          <div className="reference-kpi-grid">
            {kpiCards.map((card) => (
              <button
                key={card.key}
                type="button"
                aria-pressed={activeKpi === card.key}
                className={`reference-kpi ${card.className || ''} ${activeKpi === card.key ? 'is-active' : ''}`}
                onClick={() => setActiveKpi(card.key)}
              >
                <span>{card.label}</span>
                <strong>{card.value}</strong>
                {card.note}
                {card.visual}
              </button>
            ))}
          </div>

          <TerminalPanel
            eyebrow="Dashboard Drilldown"
            title={kpiDetail.title}
            description={kpiDetail.body}
            className="kpi-detail-panel"
            actions={<Link className="link-button" href={kpiDetail.href}>Open Workflow</Link>}
          >
            <div className="kpi-detail-metrics">
              {kpiDetail.metrics.map((item) => (
                <div key={item.label}>
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>
            <div className="kpi-detail-list">
              {kpiDetail.rows.slice(0, 8).map((row: any, index: number) => (
                <button
                  key={`${rowSymbol(row)}-${index}`}
                  type="button"
                  onClick={() => {
                    setQuery(rowSymbol(row));
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                  }}
                >
                  <span>{index + 1}</span>
                  <strong>{rowSymbol(row)}</strong>
                  <small>{row.sector || row.scan_type || row.best_horizon || 'Data source unavailable'}</small>
                  <em>{rowSignal(row)}</em>
                  <b>{rowScore(row) === null ? 'Score unavailable' : `${rowScore(row)}/100`}</b>
                  <p>{rowReason(row)}</p>
                </button>
              ))}
              {!kpiDetail.rows.length && <div className="empty-inline">No backend rows available for this detail view.</div>}
            </div>
          </TerminalPanel>

          <TerminalPanel title="Live Stock Monitor" actions={<button className="link-button" type="button" onClick={() => refreshMonitorQuotes()}><Bell size={14} /> Refresh Quotes</button>}>
            <div className="live-monitor-entry">
              <label className="field field--wide">
                <span>Add Stocks To Monitor</span>
                <input value={monitorInput} onBlur={() => setMonitorInput(parseSymbols(monitorInput).join(', '))} onChange={(event) => setMonitorInput(event.target.value)} placeholder="RELIANCE, TCS, INFY" />
              </label>
              <button className="btn-primary" type="button" onClick={addMonitorSymbols}><Plus size={15} /> Add Monitor</button>
            </div>
            <div className="live-monitor-list">
              {monitorRows.length ? monitorRows.map((row) => {
                const status = monitorStatus(row);
                return (
                  <div className="live-monitor-row" key={row.symbol}>
                    <div>
                      <strong>{row.symbol}</strong>
                      <small>{row.last_updated ? `Updated ${row.last_updated}` : row.status || 'Waiting for quote'}</small>
                    </div>
                    <label><span>LTP</span><input value={formatPrice(row.live_price)} readOnly /></label>
                    <label><span>Entry</span><input type="number" value={row.entry_price ?? ''} onChange={(event) => updateMonitor(row.symbol, { entry_price: Number(event.target.value) || undefined })} /></label>
                    <label><span>Stoploss</span><input type="number" value={row.stop_loss ?? ''} onChange={(event) => updateMonitor(row.symbol, { stop_loss: Number(event.target.value) || undefined })} /></label>
                    <label><span>Target 1</span><input type="number" value={row.target1 ?? ''} onChange={(event) => updateMonitor(row.symbol, { target1: Number(event.target.value) || undefined })} /></label>
                    <label><span>Target 2</span><input type="number" value={row.target2 ?? ''} onChange={(event) => updateMonitor(row.symbol, { target2: Number(event.target.value) || undefined })} /></label>
                    <label className="live-monitor-toggle"><span>Telegram</span><input type="checkbox" checked={row.telegram} onChange={(event) => updateMonitor(row.symbol, { telegram: event.target.checked })} /></label>
                    <span className={`status-badge ${status.tone}`}>{status.label}</span>
                    {row.telegram_status && <small className={/failed|missing|error|invalid|forbidden|unauthorized/i.test(row.telegram_status) ? 'status-bad' : 'status-good'}>{row.telegram_status}</small>}
                    <button className="btn-secondary" type="button" onClick={() => saveMonitorAlert(row)}>Save</button>
                    <button className="icon-button" type="button" title="Remove monitor" onClick={() => removeMonitor(row.symbol)}>×</button>
                  </div>
                );
              }) : <div className="empty-inline">Add stocks to monitor live price, target, stoploss, and Telegram alerts.</div>}
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

          <div className="bottom-analytics-grid">
            <TerminalPanel title="Sector Heatmap">
              <div className="sector-tile-grid">
                {sectorWidgets.length ? sectorWidgets.map((item: any) => (
                  <div className="sector-heat-tile" key={item.sector}>
                    <strong>{item.sector}</strong>
                    <span>{Number(item.profit || 0) >= 0 ? '+' : ''}{Number(item.profit || 0).toFixed(2)}%</span>
                  </div>
                )) : <div className="empty-inline">Sector data unavailable</div>}
              </div>
            </TerminalPanel>
            <TerminalPanel title="AI Risk Meter">
              {dashboardData?.risk ? (
                <div className="risk-meter">
                  <div className="risk-meter__top">
                    <span>{Math.round(Number(dashboardData.risk.score))}</span>
                    <strong>{dashboardData.risk.label}</strong>
                  </div>
                  <div className="risk-meter__bar" aria-label="AI risk score">
                    <i style={{ width: `${Math.max(0, Math.min(100, Number(dashboardData.risk.score || 0)))}%` }} />
                  </div>
                  <div className="risk-meter__scale"><small>Low</small><small>Medium</small><small>High</small></div>
                </div>
              ) : <div className="empty-inline">Risk data unavailable</div>}
            </TerminalPanel>
            <TerminalPanel title="Market Breadth">
              {breadth ? <div className="breadth-card">
                <p><span>Advances</span><strong className="status-good">{breadth.advances} ({breadth.advance_pct}%)</strong></p>
                <p><span>Declines</span><strong className="status-bad">{breadth.declines} ({breadth.decline_pct}%)</strong></p>
                <p><span>Unchanged</span><strong>{breadth.unchanged}</strong></p>
              </div> : <div className="empty-inline">Breadth data unavailable</div>}
            </TerminalPanel>
          </div>

          <TerminalPanel title="AI Insights" actions={<button className="link-button" type="button" onClick={() => handleSaveFilter('AI Insights View', { section: 'ai_insights' })}>View All Insights</button>}>
            <div className="ai-insight-strip">
              {aiInsights.map((insight: any) => (
                <button className="ai-insight-card" key={`${insight.title}-${insight.symbol}`} type="button" onClick={() => handleAlert(insight.symbol, insight.rating === 'Avoid' ? 50 : 85)}>
                  <span>{insight.title}</span>
                  <strong>{insight.symbol}</strong>
                  <p>{insight.reason}</p>
                  <b className={`signal-pill signal-pill--${String(insight.rating).toLowerCase().replace(/\s+/g, '-')}`}>{insight.rating}</b>
                </button>
              ))}
            </div>
          </TerminalPanel>

          <TerminalPanel title="Quick Actions">
            <div className="quick-action-grid">
              <button type="button" onClick={() => handleSaveFilter('Smart Screener', { min_profitability: 80, max_risk: 35 })}><Filter size={20} /><strong>Smart Screener</strong><span>Save strict profitable filter</span></button>
              <Link href="/reports"><BarChart3 size={20} /><strong>Reports</strong><span>Open report library</span></Link>
              <button type="button" disabled={!topOpportunities[0]} onClick={() => topOpportunities[0] && handleAlert(topOpportunities[0].symbol || topOpportunities[0].stock, 90)}><TrendingUp size={20} /><strong>Alerts Center</strong><span>{topOpportunities[0] ? 'Create top-pick alert' : 'No live pick available'}</span></button>
              <button type="button" disabled={!topOpportunities[0]} onClick={() => topOpportunities[0] && handlePaperTrade(topOpportunities[0].symbol || topOpportunities[0].stock, Number(topOpportunities[0].live_price))}><Star size={20} /><strong>Paper Trading</strong><span>{topOpportunities[0] ? 'Open 1-share test trade' : 'No live quote available'}</span></button>
              <Link href="/scan-center"><Grid2X2 size={20} /><strong>Backtesting</strong><span>Run validation workflow</span></Link>
            </div>
          </TerminalPanel>
        </div>

        <aside className="dashboard-right-rail">
          <TerminalPanel title="Top Opportunities" actions={<button className="link-button" type="button" onClick={() => { setSortMode('AI Score'); setDisplayLimit(25); }}>View All</button>}>
            <div className="rail-list">
              {topOpportunities.map((stock: any, index: number) => (
                <div className="rail-stock" key={`${stock.symbol || stock.stock || index}-top`}>
                  <span className="stock-logo">{String(stock.symbol || stock.stock || 'S').slice(0, 1)}</span>
                  <div><strong>{stock.symbol || stock.stock}</strong><small>{stock.sector || stock.reason || 'Data unavailable'}</small></div>
                  <button type="button" onClick={() => handleAlert(stock.symbol || stock.stock, Number(stock.ml_score || stock.confidence_pct || 0))}>{Math.round(Number(stock.ml_score || stock.confidence_pct || 0))}</button>
                </div>
              ))}
            </div>
          </TerminalPanel>
          <TerminalPanel title="My Watchlist" actions={<button className="link-button" type="button" disabled={!topOpportunities[0]} onClick={() => topOpportunities[0] && handleWatch(topOpportunities[0].symbol || topOpportunities[0].stock)}>Add Top</button>}>
            <div className="rail-list">
              {watchlistPreview.map((stock: any, index: number) => (
                <div className="rail-stock rail-stock--compact" key={`${stock.symbol || stock.stock || index}-watch`}>
                  <span className="stock-logo">{String(stock.symbol || stock.stock || 'N').slice(0, 1)}</span>
                  <div><strong>{stock.symbol || stock.stock}</strong><small>{stock.sector || 'User watchlist'}</small></div>
                  <button type="button" className="link-button status-good" onClick={() => handlePaperTrade(stock.symbol, Number(stock.live_price || 0))}>+{Number(stock.change_pct || 0).toFixed(2)}%</button>
                </div>
              ))}
            </div>
          </TerminalPanel>
          <TerminalPanel title="Recent News" actions={<button className="link-button" type="button" onClick={() => setShowAllNews((value) => !value)}>{showAllNews ? 'Show Less' : 'View All'}</button>}>
            <div className="news-list">
              {visibleNews.map((article: any) => (
                <div className="news-row" key={article.title}>
                  <BarChart3 size={15} />
                  <strong>{article.title}</strong>
                  <span>{article.category}</span>
                </div>
              ))}
            </div>
          </TerminalPanel>
        </aside>
      </section>
    </main>
  );
}
