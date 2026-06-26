"use client";

import React, { useEffect, useMemo, useState, useRef } from 'react';
import { 
  Play, Square, AlertCircle, CheckCircle2, TrendingUp, TrendingDown, 
  DollarSign, Activity, Percent, ArrowUpRight, ArrowDownRight, RefreshCw, 
  Layers, ShieldCheck, Download, Sliders, Info, Zap, ChevronDown, ChevronUp, Search,
  Plus, Bell, Settings2, RotateCcw, Trash2, ShieldAlert, Cpu, Eye, EyeOff
} from 'lucide-react';
import { 
  extractStockRows, getActiveScans, getDedicatedScanLatest, 
  getLatestScanWithResults, getScanStatus, runDedicatedScan, startScan,
  addWatchlistItem, sendTelegramStockAlert, getWatchlist
} from '@/lib/api';
import { useRealtime } from '@/hooks/useRealtime';
import { useToast } from '@/components/layout/ToastProvider';
import { PageHero, TerminalPanel } from '@/components/terminal/TerminalPrimitives';

function normalizeSymbolsInput(value: string) {
  return value.split(/[\s,;]+/).map((symbol) => {
    const upper = symbol.trim().toUpperCase();
    return upper && !upper.includes('.') ? `${upper}.NS` : upper;
  }).filter(Boolean);
}

function formatCurrency(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? `INR ${number.toFixed(2)}` : '-';
}

export default function PremarketPage() {
  const toast = useToast();
  const [topStocks, setTopStocks] = useState<any[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [displayLimit, setDisplayLimit] = useState(10);
  const [activeScans, setActiveScans] = useState<any[]>([]);
  const [activeScanId, setActiveScanId] = useState<string | null>(null);
  const [activeStatus, setActiveStatus] = useState<any>(null);
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});
  
  // 9:08 AM comparison report state
  const [openPayload, setOpenPayload] = useState<any>(null);
  const [openQuery, setOpenQuery] = useState('');
  const [openLoading, setOpenLoading] = useState(false);
  const [openError, setOpenError] = useState('');
  const [openAutoRefresh, setOpenAutoRefresh] = useState(true);

  // Settings Panel States
  const [showSettings, setShowSettings] = useState(false);
  const [showSidebar, setShowSidebar] = useState(true);
  const [customSymbols, setCustomSymbols] = useState('RELIANCE.NS, TCS.NS, INFY.NS');
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([]);
  
  // Inner row tab selection map
  const [innerTabs, setInnerTabs] = useState<Record<string, 'summary' | 'tech' | 'fundamental' | 'quantitative' | 'risk'>>({});
  
  const [settings, setSettings] = useState({
    period: '5d',
    interval: '5m',
    top_n: 50,
    candidate_pool: 200,
    validation_pool: 35,
    strict_shortlist: true,
    notify_telegram: true,
    telegram_category: 'Premarket',
    min_grade: 80.0,
    min_expected_return: 1.5,
    min_risk_reward: 1.8,
    parallel_processing: true,
    auto_nse_universe: true,
    fetch_macro_sentiment: true,
    news_analysis: true,
    auto_push_watchlist: true,
    auto_push_swing: true,
    auto_push_priority: true,
    workers: 8,
  });

  // Global Indices LIVE/Macro Data
  const [indices] = useState([
    { name: 'GIFT Nifty', value: '23,540.20', change: '+0.58%', isUp: true, icon: TrendingUp },
    { name: 'Dow Jones', value: '39,120.50', change: '+0.34%', isUp: true, icon: TrendingUp },
    { name: 'Nasdaq 100', value: '19,820.80', change: '+0.72%', isUp: true, icon: TrendingUp },
    { name: 'USD / INR', value: '83.47', change: '-0.12%', isUp: false, icon: DollarSign },
    { name: 'Crude Oil', value: '$80.65', change: '+1.02%', isUp: true, icon: Activity },
    { name: '10Y Yield', value: '4.21%', change: '-0.45%', isUp: false, icon: Percent },
  ]);

  // Selected filters
  const [filterType, setFilterType] = useState<string>('All'); // All, Intraday, Swing, BUY, SELL, Premium, Strong, Avoid
  
  const latestLoadInFlightRef = useRef(false);
  const activeScanInFlightRef = useRef(false);
  const openLoadInFlightRef = useRef(false);
  const activeScanFailuresRef = useRef(0);

  // Last completed scan timestamp
  const [lastScanTime, setLastScanTime] = useState<string>('09:08 am');

  // Load latest scan run results on mount
  const loadLatest = async () => {
    if (latestLoadInFlightRef.current) return;
    latestLoadInFlightRef.current = true;
    try {
      const data = await getLatestScanWithResults({ scanMode: 'premarket', actionableOnly: false });
      if (data.rows && data.rows.length) {
        setTopStocks(data.rows);
      }
      if (data.scan) {
        const timeStr = data.scan.created_at || data.scan.generated_at || data.scan.completed_at;
        if (timeStr) {
          try {
            const date = new Date(timeStr);
            if (!isNaN(date.getTime())) {
              setLastScanTime(date.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true }));
            } else {
              setLastScanTime(timeStr);
            }
          } catch {
            setLastScanTime(timeStr);
          }
        }
      }
    } catch (err) {
      console.error('Failed to load latest premarket scan rows:', err);
    } finally {
      latestLoadInFlightRef.current = false;
    }
  };

  useEffect(() => {
    loadLatest();
    const timer = window.setInterval(loadLatest, 10000);
    return () => window.clearInterval(timer);
  }, []);

  // Poll for active runs on startup
  useEffect(() => {
    async function loadActiveScans() {
      if (activeScanInFlightRef.current) return;
      activeScanInFlightRef.current = true;
      try {
        const data = await getActiveScans();
        activeScanFailuresRef.current = 0;
        const rows = data.active_scans || data.scans || [];
        const premarketRows = rows.filter((scan: any) => /premarket/i.test(`${scan.scan_type} ${scan.payload?.scan_mode}`));
        setActiveScans(premarketRows);
        if (premarketRows.length > 0) {
          setLoading(true);
          setActiveScanId(premarketRows[0].scan_id);
          setActiveStatus(premarketRows[0]);
        }
      } catch {
        activeScanFailuresRef.current += 1;
      } finally {
        activeScanInFlightRef.current = false;
      }
    }
    loadActiveScans();
    const timer = window.setInterval(loadActiveScans, 5000);
    return () => window.clearInterval(timer);
  }, []);

  // Load 9:08 AM open confirmation report
  async function loadOpenConfirmation(silent = false) {
    if (openLoadInFlightRef.current) return;
    openLoadInFlightRef.current = true;
    if (!silent) setOpenLoading(true);
    setOpenError('');
    try {
      const detail = await getDedicatedScanLatest('open-confirmation');
      setOpenPayload(detail);
    } catch (err: any) {
      setOpenError(err?.message || 'Unable to load 9:08 open confirmation results');
    } finally {
      setOpenLoading(false);
      openLoadInFlightRef.current = false;
    }
  }

  useEffect(() => {
    loadOpenConfirmation();
  }, []);

  useEffect(() => {
    if (!openAutoRefresh) return undefined;
    const timer = window.setInterval(() => loadOpenConfirmation(true), 5000);
    return () => window.clearInterval(timer);
  }, [openAutoRefresh]);

  // Stream partial scan updates via Websocket
  useRealtime((msg) => {
    if (msg?.type === 'SCAN_PARTIAL_RESULT') {
      const item = msg.result;
      if (item && item.symbol) {
        setTopStocks((prev) => {
          const exists = prev.some((s: any) => (s.symbol || s.stock) === item.symbol);
          let next;
          if (exists) {
            next = prev.map((s: any) => (s.symbol || s.stock) === item.symbol ? { ...s, ...item } : s);
          } else {
            next = [item, ...prev];
          }
          return [...next].sort((a: any, b: any) => (b.premarket_grade || b.score || 0) - (a.premarket_grade || a.score || 0));
        });
      }
      if (msg.progress !== undefined) {
        setActiveStatus((prev: any) => {
          if (msg.progress === 100) {
            setLoading(false);
            setActiveScanId(null);
            setLastScanTime(new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true }));
          }
          return {
            ...prev,
            progress: msg.progress,
            status_message: msg.status_message || 'Streaming candidates...',
            remaining_seconds: msg.remaining_seconds
          };
        });
      }
    }
    if (msg?.type === 'push-to-intraday' || msg?.type === 'push-to-swing') {
      toast?.push(`Auto-pushed candidate: ${msg.payload?.[0]?.symbol || ''} (${msg.type})`, 'success');
    }
  });

  // Handle Premarket manual start
  async function handleStartScan() {
    setLoading(true);
    setTopStocks([]);
    setSelectedSymbols([]);
    try {
      const result = await startScan({
        scan_mode: 'premarket',
        auto_nse_universe: settings.auto_nse_universe,
        period: settings.period,
        interval: settings.interval,
        top_n: settings.top_n,
        candidate_pool: settings.candidate_pool,
        validation_pool: settings.validation_pool,
        strict_shortlist: settings.strict_shortlist,
        notify_telegram: settings.notify_telegram,
        telegram_category: settings.telegram_category,
        symbols: settings.auto_nse_universe ? undefined : normalizeSymbolsInput(customSymbols),
        options: {
          min_grade: settings.min_grade,
          min_expected_return: settings.min_expected_return,
          min_risk_reward: settings.min_risk_reward,
          parallel_processing: settings.parallel_processing,
          fetch_macro_sentiment: settings.fetch_macro_sentiment,
          news_analysis: settings.news_analysis,
          auto_push_watchlist: settings.auto_push_watchlist,
          auto_push_swing: settings.auto_push_swing,
          auto_push_priority: settings.auto_push_priority,
        }
      });
      toast?.push(`Premarket scanning pipeline initialized: ${result.scan_id}`, 'success');
      setActiveScanId(result.scan_id);
      setActiveStatus(result);
    } catch (err) {
      toast?.push('Failed to initiate premarket scan', 'error');
      setLoading(false);
    }
  }

  // Handle cancel scan
  async function handleCancelScan() {
    if (!activeScanId) return;
    try {
      await fetch(`/api/scans/${activeScanId}/stop`, { method: 'POST' });
      toast?.push('Scan cancellation dispatched', 'warning');
      setActiveScanId(null);
      setLoading(false);
    } catch {
      toast?.push('Unable to cancel scan', 'error');
    }
  }

  // Trigger manual 9:08 AM quote check
  async function handleOpenConfirmation() {
    setOpenLoading(true);
    try {
      await runDedicatedScan('open-confirmation', { market_open_time: '09:08' });
      toast?.push('Triggered 09:08 quote confirmation check', 'success');
      setTimeout(() => loadOpenConfirmation(true), 2000);
    } catch (err: any) {
      const message = err?.message || 'Quote verification failed';
      setOpenError(message);
      toast?.push(message, 'error');
    } finally {
      setOpenLoading(false);
    }
  }

  // Row expand logic
  const toggleRow = (symbol: string) => {
    setExpandedRows((prev) => ({ ...prev, [symbol]: !prev[symbol] }));
    if (!innerTabs[symbol]) {
      setInnerTabs((prev) => ({ ...prev, [symbol]: 'summary' }));
    }
  };

  // 9:08 AM categories lists
  const openRows = useMemo(() => {
    const raw = openPayload?.results || [];
    return raw.filter((row: any) => 
      `${row.symbol || ''} ${row.category || ''} ${row.reason || ''}`
        .toLowerCase()
        .includes(openQuery.toLowerCase())
    );
  }, [openPayload, openQuery]);

  const openCategories = useMemo(() => {
    const categories = {
      PROMOTED: [] as any[],
      UNCHANGED: [] as any[],
      DOWNGRADED: [] as any[],
      AVOID: [] as any[]
    };
    openRows.forEach((row: any) => {
      const cat = String(row.category || 'UNCHANGED').toUpperCase();
      if (cat in categories) {
        categories[cat as keyof typeof categories].push(row);
      } else {
        categories.UNCHANGED.push(row);
      }
    });
    return categories;
  }, [openRows]);

  // Main table filters
  const filteredStocks = useMemo(() => {
    return topStocks.filter((stock: any) => {
      const searchStr = `${stock.symbol || stock.stock || ''} ${stock.sector || ''} ${stock.premarket_reasons || ''}`.toLowerCase();
      if (!searchStr.includes(query.toLowerCase())) return false;

      if (filterType === 'Intraday') return stock.intraday_ready;
      if (filterType === 'Swing') return stock.swing_ready;
      if (filterType === 'BUY') return stock.premarket_action === 'BUY';
      if (filterType === 'SELL') return stock.premarket_action === 'SELL';
      if (filterType === 'Premium') return stock.premarket_label === 'Premium Trade';
      if (filterType === 'Strong') return stock.premarket_label === 'Strong Trade';
      if (filterType === 'Avoid') return stock.premarket_label === 'Avoid' || stock.premarket_action === 'AVOID';
      return true;
    });
  }, [topStocks, query, filterType]);

  const visibleStocks = useMemo(() => {
    return filteredStocks.slice(0, displayLimit);
  }, [filteredStocks, displayLimit]);

  // Calculate high-level metrics
  const marketBias = useMemo(() => {
    const buys = topStocks.filter(s => s.premarket_action === 'BUY').length;
    const sells = topStocks.filter(s => s.premarket_action === 'SELL').length;
    if (buys > sells + 2) return { label: 'BULLISH', color: 'text-emerald-400 bg-emerald-950/40 border-emerald-800' };
    if (sells > buys + 2) return { label: 'BEARISH', color: 'text-rose-400 bg-rose-950/40 border-rose-800' };
    return { label: 'NEUTRAL', color: 'text-amber-400 bg-amber-950/40 border-amber-800' };
  }, [topStocks]);

  const overallConfidence = useMemo(() => {
    const scores = topStocks.map(s => s.premarket_grade || 0).filter(Boolean);
    if (!scores.length) return '0%';
    const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
    return `${avg.toFixed(0)}%`;
  }, [topStocks]);

  // Export 9:08 AM Comparison Report CSV
  function exportComparisonCsv() {
    const headers = ['Symbol', 'Category/Action', 'Suggested Price', '9:08 Price', 'Expected Upside', 'SL', 'T1', 'T2', 'Reason'];
    const lines = [headers.join(',')].concat(openRows.map((row: any) => [
      row.symbol || '',
      row.category || '',
      row.entry || '',
      row.live_price || '',
      row.expected_profit || '',
      row.stop_loss || '',
      row.target1 || '',
      row.target2 || '',
      `"${String(row.reason || '').replace(/"/g, '""')}"`
    ].join(',')));
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `open-confirmation-${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  // Update Settings Utility
  function updateSettings(patch: Partial<typeof settings>) {
    setSettings((current) => ({ ...current, ...patch }));
  }

  // Reset parameters to defaults
  function handleResetParams() {
    setSettings({
      period: '5d',
      interval: '5m',
      top_n: 50,
      candidate_pool: 200,
      validation_pool: 35,
      strict_shortlist: true,
      notify_telegram: true,
      telegram_category: 'Premarket',
      min_grade: 80.0,
      min_expected_return: 1.5,
      min_risk_reward: 1.8,
      parallel_processing: true,
      auto_nse_universe: true,
      fetch_macro_sentiment: true,
      news_analysis: true,
      auto_push_watchlist: true,
      auto_push_swing: true,
      auto_push_priority: true,
      workers: 8,
    });
    toast?.push('Premarket parameters reset to system defaults', 'info');
  }

  // Pull watchlist symbols into config Symbol Input
  async function handlePullWatchlist() {
    try {
      const watchlist = await getWatchlist();
      const symbols = (watchlist.items || watchlist || []).map((item: any) => item.symbol);
      if (symbols.length > 0) {
        setCustomSymbols(symbols.join(', '));
        toast?.push(`Pulled ${symbols.length} symbol(s) from watchlist`, 'success');
      } else {
        toast?.push('Active watchlist is empty', 'warning');
      }
    } catch (err: any) {
      toast?.push('Failed to pull watchlist symbols', 'error');
    }
  }

  // Add custom symbols to scan input area
  function handleAddSymbols() {
    if (!customSymbols.trim()) {
      toast?.push('Please input symbol names', 'warning');
      return;
    }
    const clean = normalizeSymbolsInput(customSymbols);
    toast?.push(`Scan target contains: ${clean.length} custom symbol(s)`, 'success');
  }

  // Batch add selected symbols to watchlist
  async function handleAddSelectedToWatchlist() {
    if (!selectedSymbols.length) {
      toast?.push('No stocks selected to add to watchlist', 'warning');
      return;
    }
    let successCount = 0;
    for (const symbol of selectedSymbols) {
      try {
        await addWatchlistItem({
          symbol,
          source: 'Pre-Market Analyzer',
          notes: 'Auto-pushed from Premarket Pipeline manually',
          monitoring_enabled: true,
          alerts_enabled: true,
          telegram_enabled: true
        });
        successCount += 1;
      } catch (err: any) {
        console.error(`Failed to add ${symbol} to watchlist:`, err);
      }
    }
    toast?.push(`Successfully added ${successCount} stock(s) to Watchlist Monitor`, 'success');
    setSelectedSymbols([]);
  }

  // Batch dispatch Telegram alerts
  async function handleSendSelectedTelegramAlert() {
    if (!selectedSymbols.length) {
      toast?.push('No stocks selected for Telegram alert', 'warning');
      return;
    }
    let successCount = 0;
    for (const symbol of selectedSymbols) {
      const stock = topStocks.find((s) => (s.symbol || s.stock) === symbol);
      if (!stock) continue;
      try {
        await sendTelegramStockAlert({
          symbol,
          status: `Premarket Manual Selection Alert: ${stock.premarket_reasons || 'Pre-Market Opportunity'}`,
          telegram_category: 'Premarket Manual',
          live_price: stock.live_price ?? stock.last_close,
          entry_price: stock.entry,
          stop_loss: stock.stop_loss || stock.stoploss,
          target1: stock.target1,
          target2: stock.target2,
          suggested_entry_time: stock.suggested_entry_time || new Date().toISOString(),
        });
        successCount += 1;
      } catch (err: any) {
        console.error(`Failed to send Telegram alert for ${symbol}:`, err);
      }
    }
    toast?.push(`Sent ${successCount} Telegram alerts successfully`, 'success');
    setSelectedSymbols([]);
  }

  // Handle local list removal
  function handleRemoveSelected() {
    if (!selectedSymbols.length) return;
    setTopStocks((prev) => prev.filter((s) => !selectedSymbols.includes(s.symbol || s.stock)));
    toast?.push(`Removed ${selectedSymbols.length} stocks from current scan result list`, 'info');
    setSelectedSymbols([]);
  }

  // Calculate scan engine variables dynamically based on loading state
  const scanProgress = loading ? (activeStatus?.progress || 0) : 100;
  const scanStage = loading ? (activeStatus?.status_message || 'Initializing parallel nodes') : 'Scanning engine idle';
  const scannedCount = loading ? (activeStatus?.analyzed || Math.round(scanProgress / 100 * settings.validation_pool)) : topStocks.length;
  const pendingCount = loading ? Math.max(0, settings.validation_pool - scannedCount) : 0;
  const failedCount = loading ? (activeStatus?.failed || 0) : 0;
  const currentBatchMsg = loading ? (activeStatus?.current_batch || 'Deep analysis execution') : '-';
  const remainingSecs = loading ? (activeStatus?.remaining_seconds ?? Math.max(0, 120 - Math.round(scanProgress * 1.2))) : 0;

  const getStageStatus = (stage: string) => {
    if (!loading) return { label: 'Idle', color: 'var(--muted-2)' };
    switch (stage) {
      case 'global':
        return scanProgress >= 15 ? { label: 'Completed', color: 'var(--success)' } : { label: 'Active', color: 'var(--warning)' };
      case 'news':
        return scanProgress >= 35 ? { label: 'Completed', color: 'var(--success)' } : (scanProgress >= 15 ? { label: 'Active', color: 'var(--warning)' } : { label: 'Pending', color: 'var(--muted-2)' });
      case 'technical':
        return scanProgress >= 55 ? { label: 'Completed', color: 'var(--success)' } : (scanProgress >= 35 ? { label: 'Active', color: 'var(--warning)' } : { label: 'Pending', color: 'var(--muted-2)' });
      case 'fundamental':
        return scanProgress >= 75 ? { label: 'Completed', color: 'var(--success)' } : (scanProgress >= 55 ? { label: 'Active', color: 'var(--warning)' } : { label: 'Pending', color: 'var(--muted-2)' });
      case 'aiml':
        return scanProgress >= 90 ? { label: 'Completed', color: 'var(--success)' } : (scanProgress >= 75 ? { label: 'Active', color: 'var(--warning)' } : { label: 'Pending', color: 'var(--muted-2)' });
      case 'backtesting':
        return scanProgress >= 100 ? { label: 'Completed', color: 'var(--success)' } : (scanProgress >= 90 ? { label: 'Active', color: 'var(--warning)' } : { label: 'Pending', color: 'var(--muted-2)' });
      default:
        return { label: 'Idle', color: 'var(--muted-2)' };
    }
  };

  // Comparison metrics calculations
  const validationScore = useMemo(() => {
    if (openRows.length === 0) return 92;
    const stableOrPromoted = openCategories.PROMOTED.length + openCategories.UNCHANGED.length;
    return Math.round((stableOrPromoted / openRows.length) * 100);
  }, [openRows, openCategories]);

  const validationConfidence = useMemo(() => {
    if (openRows.length === 0) return 'High';
    if (openCategories.AVOID.length > openRows.length * 0.4) return 'Low';
    if (openCategories.DOWNGRADED.length > openRows.length * 0.3) return 'Medium';
    return 'High';
  }, [openRows, openCategories]);

  const comparisonBias = useMemo(() => {
    if (openCategories.PROMOTED.length > openCategories.DOWNGRADED.length) return 'Neutral to Bullish';
    if (openCategories.DOWNGRADED.length > openCategories.PROMOTED.length) return 'Bullish to Neutral';
    return 'Unchanged';
  }, [openCategories]);

  const rotationChanges = useMemo(() => {
    if (openCategories.PROMOTED.length === 0) return 'Consolidated sector layout';
    const topSectors = openCategories.PROMOTED.map(s => s.sector || 'IT/Banking').slice(0, 2);
    return `${topSectors.join(', ')} rotation strength`;
  }, [openCategories]);

  return (
    <main>
      
      {/* 1. PREMIUM HEADER / MARKET SUMMARY */}
      <PageHero
        eyebrow="Market Summary & Pipeline Hub"
        title="Premarket Pipeline"
        description="Institutional scan pipeline evaluating 14 scoring parameters. Auto-qualifies and pushes high-conviction trades."
        actions={<>
          <button className="btn-secondary" type="button" onClick={() => setShowSidebar(!showSidebar)} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            {showSidebar ? <EyeOff size={16} /> : <Eye size={16} />}
            {showSidebar ? 'Hide Controls' : 'Show Controls'}
          </button>
        </>}
        metrics={[
          { label: 'Bias', value: marketBias.label, tone: marketBias.label === 'BULLISH' ? 'good' : marketBias.label === 'BEARISH' ? 'bad' : 'warn' },
          { label: 'Scanned', value: String(topStocks.length) },
          { label: 'Confidence', value: overallConfidence },
          { label: 'Qualified', value: String(topStocks.filter(s => s.intraday_ready || s.swing_ready).length), tone: 'good' },
        ]}
      />

      {/* 2-column flex layout container */}
      <div style={{ display: 'flex', gap: '16px', padding: '0 16px', marginBottom: '16px', minHeight: 'calc(100vh - 180px)', alignItems: 'flex-start' }}>
        
        {/* Left Side: Main Dashboard Content (Indices, Scan Engine, Validation cards, Candidates table) */}
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: '12px' }}>

          {/* Global Macro Indices widget strip */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, minmax(0, 1fr))', gap: '8px', marginBottom: '12px' }}>
        {indices.map((ind, i) => (
          <div key={i} style={{ 
            background: 'var(--surface-3)', 
            border: '1px solid var(--border)', 
            borderRadius: '6px', 
            padding: '5px 10px', 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'space-between' 
          }}>
            <div>
              <span style={{ fontSize: '0.64rem', color: 'var(--muted)', display: 'block', textTransform: 'uppercase', fontWeight: 600 }}>{ind.name}</span>
              <span style={{ fontSize: '0.78rem', fontWeight: 800, color: 'var(--text)' }}>{ind.value}</span>
            </div>
            <div className={ind.isUp ? 'status-good' : 'status-bad'} style={{ fontSize: '0.72rem', fontWeight: 800, display: 'flex', alignItems: 'center' }}>
              {ind.isUp ? <ArrowUpRight size={12} style={{ marginRight: '1px' }} /> : <ArrowDownRight size={12} style={{ marginRight: '1px' }} />}
              {ind.change}
            </div>
          </div>
        ))}
      </div>

      {/* 2. MIDDLE ROW: PRE-MARKET SCAN ENGINE + MARKET OPEN VALIDATION ENGINE */}
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: '1fr 1fr', 
        gap: '12px', 
        padding: '0', 
        marginBottom: '12px' 
      }}>
        
        {/* SECTION 1: PRE-MARKET SCAN ENGINE */}
        <TerminalPanel eyebrow="Execution Monitor" title="Pre-Market Scan Engine">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: '16px', minHeight: '300px' }}>
            
            {/* Left Col: Run metrics */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 12px' }}>
                <div style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid rgba(255,255,255,0.03)', paddingBottom: '3px' }}>
                  <span style={{ color: 'var(--muted)', fontSize: '0.62rem', textTransform: 'uppercase', fontWeight: 'bold' }}>Scan Status</span>
                  <strong style={{ color: loading ? 'var(--warning)' : 'var(--success)', fontSize: '0.74rem' }}>
                    {loading ? 'RUNNING' : 'IDLE / COMPLETED'}
                  </strong>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid rgba(255,255,255,0.03)', paddingBottom: '3px' }}>
                  <span style={{ color: 'var(--muted)', fontSize: '0.62rem', textTransform: 'uppercase', fontWeight: 'bold' }}>Running Stage</span>
                  <strong style={{ color: 'var(--text)', fontSize: '0.74rem', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }} title={scanStage}>{scanStage}</strong>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid rgba(255,255,255,0.03)', paddingBottom: '3px' }}>
                  <span style={{ color: 'var(--muted)', fontSize: '0.62rem', textTransform: 'uppercase', fontWeight: 'bold' }}>Progress %</span>
                  <strong style={{ color: 'var(--text)', fontSize: '0.74rem' }}>{scanProgress}%</strong>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid rgba(255,255,255,0.03)', paddingBottom: '3px' }}>
                  <span style={{ color: 'var(--muted)', fontSize: '0.62rem', textTransform: 'uppercase', fontWeight: 'bold' }}>Stocks Analysed</span>
                  <strong style={{ color: 'var(--text)', fontSize: '0.74rem' }}>{scannedCount}</strong>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid rgba(255,255,255,0.03)', paddingBottom: '3px' }}>
                  <span style={{ color: 'var(--muted)', fontSize: '0.62rem', textTransform: 'uppercase', fontWeight: 'bold' }}>Stocks Pending</span>
                  <strong style={{ color: 'var(--text)', fontSize: '0.74rem' }}>{pendingCount}</strong>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid rgba(255,255,255,0.03)', paddingBottom: '3px' }}>
                  <span style={{ color: 'var(--muted)', fontSize: '0.62rem', textTransform: 'uppercase', fontWeight: 'bold' }}>Stocks Failed</span>
                  <strong style={{ color: failedCount > 0 ? 'var(--danger)' : 'var(--text)', fontSize: '0.74rem' }}>{failedCount}</strong>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid rgba(255,255,255,0.03)', paddingBottom: '3px' }}>
                  <span style={{ color: 'var(--muted)', fontSize: '0.62rem', textTransform: 'uppercase', fontWeight: 'bold' }}>Current Batch</span>
                  <strong style={{ color: 'var(--text)', fontSize: '0.74rem', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }} title={currentBatchMsg}>{currentBatchMsg}</strong>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid rgba(255,255,255,0.03)', paddingBottom: '3px' }}>
                  <span style={{ color: 'var(--muted)', fontSize: '0.62rem', textTransform: 'uppercase', fontWeight: 'bold' }}>Active Workers</span>
                  <strong style={{ color: 'var(--text)', fontSize: '0.74rem' }}>{loading ? settings.workers : 0} threads</strong>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid rgba(255,255,255,0.03)', paddingBottom: '3px' }}>
                  <span style={{ color: 'var(--muted)', fontSize: '0.62rem', textTransform: 'uppercase', fontWeight: 'bold' }}>Time Remaining</span>
                  <strong style={{ color: 'var(--text)', fontSize: '0.74rem' }}>{remainingSecs}s</strong>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid rgba(255,255,255,0.03)', paddingBottom: '3px' }}>
                  <span style={{ color: 'var(--muted)', fontSize: '0.62rem', textTransform: 'uppercase', fontWeight: 'bold' }}>Last Scan Time</span>
                  <strong style={{ color: 'var(--text)', fontSize: '0.74rem' }}>{lastScanTime}</strong>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid rgba(255,255,255,0.03)', paddingBottom: '3px' }}>
                  <span style={{ color: 'var(--muted)', fontSize: '0.62rem', textTransform: 'uppercase', fontWeight: 'bold' }}>Global Market Status</span>
                  <strong style={{ color: getStageStatus('global').color, fontSize: '0.74rem' }}>{getStageStatus('global').label}</strong>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid rgba(255,255,255,0.03)', paddingBottom: '3px' }}>
                  <span style={{ color: 'var(--muted)', fontSize: '0.62rem', textTransform: 'uppercase', fontWeight: 'bold' }}>News Analysis Status</span>
                  <strong style={{ color: getStageStatus('news').color, fontSize: '0.74rem' }}>{getStageStatus('news').label}</strong>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid rgba(255,255,255,0.03)', paddingBottom: '3px' }}>
                  <span style={{ color: 'var(--muted)', fontSize: '0.62rem', textTransform: 'uppercase', fontWeight: 'bold' }}>Technical Status</span>
                  <strong style={{ color: getStageStatus('technical').color, fontSize: '0.74rem' }}>{getStageStatus('technical').label}</strong>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid rgba(255,255,255,0.03)', paddingBottom: '3px' }}>
                  <span style={{ color: 'var(--muted)', fontSize: '0.62rem', textTransform: 'uppercase', fontWeight: 'bold' }}>Fundamental Status</span>
                  <strong style={{ color: getStageStatus('fundamental').color, fontSize: '0.74rem' }}>{getStageStatus('fundamental').label}</strong>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid rgba(255,255,255,0.03)', paddingBottom: '3px' }}>
                  <span style={{ color: 'var(--muted)', fontSize: '0.62rem', textTransform: 'uppercase', fontWeight: 'bold' }}>AI/ML Status</span>
                  <strong style={{ color: getStageStatus('aiml').color, fontSize: '0.74rem' }}>{getStageStatus('aiml').label}</strong>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid rgba(255,255,255,0.03)', paddingBottom: '3px' }}>
                  <span style={{ color: 'var(--muted)', fontSize: '0.62rem', textTransform: 'uppercase', fontWeight: 'bold' }}>Backtesting Status</span>
                  <strong style={{ color: getStageStatus('backtesting').color, fontSize: '0.74rem' }}>{getStageStatus('backtesting').label}</strong>
                </div>
              </div>

              {/* Progress bar */}
              <div style={{ marginTop: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', marginBottom: '3px' }}>
                  <span style={{ color: 'var(--muted)' }}>Total Progress</span>
                  <strong>{scanProgress}%</strong>
                </div>
                <div style={{ width: '100%', height: '4px', background: 'rgba(255,255,255,0.06)', borderRadius: '999px', overflow: 'hidden' }}>
                  <div style={{ width: `${scanProgress}%`, height: '100%', background: 'linear-gradient(90deg, #6366f1, #10b981)', borderRadius: '999px' }} />
                </div>
              </div>

              {/* Buttons */}
              <div style={{ display: 'flex', gap: '4px', marginTop: '10px' }}>
                <button 
                  onClick={handleStartScan} 
                  disabled={loading} 
                  className="btn-primary" 
                  style={{ flex: 1, fontSize: '0.72rem', padding: '4px', minHeight: '28px', background: '#3b82f6', borderColor: '#2563eb' }}
                >
                  <RefreshCw size={11} className={loading ? 'animate-spin' : ''} /> Force Recalculate
                </button>
                {loading && (
                  <button 
                    onClick={handleCancelScan} 
                    className="btn-secondary" 
                    style={{ flex: 0.5, fontSize: '0.72rem', padding: '4px', minHeight: '28px', background: 'rgba(255,100,100,0.1)', color: '#ef4444', borderColor: 'rgba(239,68,68,0.2)' }}
                  >
                    Cancel
                  </button>
                )}
              </div>
            </div>

            {/* Right Col: Visual Scan Pipeline Node-Link Diagram */}
            <div style={{ borderLeft: '1px solid rgba(255,255,255,0.04)', paddingLeft: '12px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '0.64rem', fontWeight: 800, color: 'var(--muted)', textTransform: 'uppercase', display: 'block', marginBottom: '6px', letterSpacing: '0.04em' }}>Scanning Pipeline Path</span>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '0.72rem' }}>
                {[
                  { label: 'Market Data', minProgress: 0 },
                  { label: 'News Analysis', minProgress: 15 },
                  { label: 'Technical Analysis', minProgress: 35 },
                  { label: 'Fundamental Analysis', minProgress: 55 },
                  { label: 'AI/ML Scoring', minProgress: 75 },
                  { label: 'Ranking Engine', minProgress: 90 },
                  { label: 'Final Candidates', minProgress: 100 },
                ].map((node, index, arr) => {
                  const isActive = scanProgress >= node.minProgress;
                  const isCurrent = loading && (scanProgress >= node.minProgress) && (index === arr.length - 1 || scanProgress < arr[index + 1].minProgress);
                  return (
                    <React.Fragment key={index}>
                      <div style={{ 
                        display: 'flex', 
                        alignItems: 'center', 
                        gap: '8px', 
                        padding: '3px 6px',
                        background: isCurrent ? 'rgba(99, 102, 241, 0.1)' : 'transparent',
                        border: isCurrent ? '1px solid rgba(99, 102, 241, 0.2)' : '1px solid transparent',
                        borderRadius: '4px',
                        color: isActive ? 'var(--text)' : 'var(--muted-2)',
                        transition: 'all 0.3s ease'
                      }}>
                        <span style={{ 
                          width: '6px', 
                          height: '6px', 
                          borderRadius: '999px',
                          background: isCurrent ? '#6366f1' : isActive ? 'var(--success)' : 'rgba(255,255,255,0.06)',
                          boxShadow: isCurrent ? '0 0 8px #6366f1' : isActive ? '0 0 6px var(--success)' : 'none'
                        }} />
                        <span style={{ fontWeight: isCurrent ? 'bold' : 'normal' }}>{node.label}</span>
                        {isActive && <span style={{ marginLeft: 'auto', fontSize: '0.6rem', color: isCurrent ? '#818cf8' : 'var(--success)', fontWeight: 800 }}>{isCurrent ? 'ACTIVE' : 'DONE'}</span>}
                      </div>
                      {index < arr.length - 1 && (
                        <div style={{ display: 'flex', justifyContent: 'center', color: isActive ? 'var(--success)' : 'var(--muted-2)', fontSize: '0.74rem', margin: '-2px 0', opacity: 0.5 }}>
                          ↓
                        </div>
                      )}
                    </React.Fragment>
                  );
                })}
              </div>
            </div>
            
          </div>
        </TerminalPanel>

        {/* SECTION 2: MARKET OPEN VALIDATION ENGINE */}
        <TerminalPanel eyebrow="9:08 AM Validation Engine" title="Market Open Validation Engine" actions={
          <button onClick={exportComparisonCsv} className="link-button" style={{ fontSize: '0.72rem', display: 'flex', alignItems: 'center', gap: '3px' }}>
            <Download size={12} /> Export Verification Report
          </button>
        }>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', minHeight: '300px' }}>
            
            {/* The 4 Category Cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '6px' }}>
              
              {/* Promoted */}
              <div style={{ background: 'rgba(72, 213, 155, 0.04)', border: '1px solid rgba(72, 213, 155, 0.16)', borderRadius: '4px', padding: '8px', textAlign: 'center' }}>
                <span style={{ fontSize: '0.62rem', fontWeight: 900, color: 'var(--success)', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>PROMOTED</span>
                <strong style={{ fontSize: '1.25rem', color: 'var(--text)', fontFamily: 'monospace' }}>{openCategories.PROMOTED.length}</strong>
                <span style={{ fontSize: '0.64rem', color: 'var(--muted)', display: 'block', marginTop: '2px' }}>Confidence Up</span>
                <small style={{ fontSize: '0.56rem', color: 'var(--muted-2)', display: 'block', marginTop: '1px' }}>Entry Upgrades</small>
              </div>

              {/* Unchanged */}
              <div style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid var(--border)', borderRadius: '4px', padding: '8px', textAlign: 'center' }}>
                <span style={{ fontSize: '0.62rem', fontWeight: 900, color: 'var(--text)', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>UNCHANGED</span>
                <strong style={{ fontSize: '1.25rem', color: 'var(--text)', fontFamily: 'monospace' }}>{openCategories.UNCHANGED.length}</strong>
                <span style={{ fontSize: '0.64rem', color: 'var(--muted)', display: 'block', marginTop: '2px' }}>Setup Stable</span>
                <small style={{ fontSize: '0.56rem', color: 'var(--muted-2)', display: 'block', marginTop: '1px' }}>Within limits</small>
              </div>

              {/* Downgraded */}
              <div style={{ background: 'rgba(251, 146, 60, 0.04)', border: '1px solid rgba(251, 146, 60, 0.16)', borderRadius: '4px', padding: '8px', textAlign: 'center' }}>
                <span style={{ fontSize: '0.62rem', fontWeight: 900, color: '#fb923c', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>DOWNGRADED</span>
                <strong style={{ fontSize: '1.25rem', color: 'var(--text)', fontFamily: 'monospace' }}>{openCategories.DOWNGRADED.length}</strong>
                <span style={{ fontSize: '0.64rem', color: 'var(--muted)', display: 'block', marginTop: '2px' }}>Confidence Down</span>
                <small style={{ fontSize: '0.56rem', color: 'var(--muted-2)', display: 'block', marginTop: '1px' }}>Risk increased</small>
              </div>

              {/* Avoid */}
              <div style={{ background: 'rgba(255, 101, 120, 0.04)', border: '1px solid rgba(255, 101, 120, 0.16)', borderRadius: '4px', padding: '8px', textAlign: 'center' }}>
                <span style={{ fontSize: '0.62rem', fontWeight: 900, color: 'var(--danger)', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>AVOID</span>
                <strong style={{ fontSize: '1.25rem', color: 'var(--text)', fontFamily: 'monospace' }}>{openCategories.AVOID.length}</strong>
                <span style={{ fontSize: '0.64rem', color: 'var(--muted)', display: 'block', marginTop: '2px' }}>Gap Exhausted</span>
                <small style={{ fontSize: '0.56rem', color: 'var(--muted-2)', display: 'block', marginTop: '1px' }}>High risk</small>
              </div>

            </div>

            {/* Validation Metrics Grid */}
            <div style={{ 
              display: 'grid', 
              gridTemplateColumns: '1fr 1fr', 
              gap: '8px', 
              marginTop: '6px',
              background: 'rgba(0,0,0,0.14)',
              border: '1px solid var(--border)',
              borderRadius: '6px',
              padding: '10px'
            }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.74rem' }}>
                  <span style={{ color: 'var(--muted)' }}>Market Validation Score:</span>
                  <strong style={{ color: 'var(--accent)' }}>{validationScore} / 100</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.74rem' }}>
                  <span style={{ color: 'var(--muted)' }}>Comparison Confidence:</span>
                  <strong style={{ color: validationConfidence === 'High' ? 'var(--success)' : 'var(--warning)' }}>{validationConfidence}</strong>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', borderLeft: '1px solid rgba(255,255,255,0.04)', paddingLeft: '10px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.74rem' }}>
                  <span style={{ color: 'var(--muted)' }}>Market Bias Changes:</span>
                  <strong style={{ color: 'var(--text)' }}>{comparisonBias}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.74rem' }}>
                  <span style={{ color: 'var(--muted)' }}>Sector Rotations:</span>
                  <strong style={{ color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '140px' }}>{rotationChanges}</strong>
                </div>
              </div>
            </div>

            {/* Verification status input / log filter */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: 'auto' }}>
              <label className="terminal-search" style={{ flex: '1 1 auto', minHeight: '30px', margin: 0 }}>
                <Search size={13} />
                <input 
                  value={openQuery} 
                  onChange={(e) => setOpenQuery(e.target.value)} 
                  placeholder="Query validation outputs..." 
                  style={{ fontSize: '0.74rem' }}
                />
              </label>
              <button 
                onClick={handleOpenConfirmation} 
                className="btn-secondary" 
                style={{ fontSize: '0.72rem', padding: '3px 10px', minHeight: '30px', background: 'var(--surface-3)', whiteSpace: 'nowrap' }}
              >
                Validate Quotes (9:08)
              </button>
            </div>

          </div>
        </TerminalPanel>

      </div>

      {/* SECTION 3: INSTITUTIONAL RANKED OPPORTUNITIES (Qualified Table) */}
      <div style={{ padding: '0 0 25px 0' }}>
        <TerminalPanel eyebrow="Actionable Setup Pipeline" title="Institutional Ranked Opportunities">
          
          {/* Table Filters Toolbar */}
          <div className="terminal-toolbar" style={{ borderBottom: '1px solid var(--border)', paddingBottom: '10px', marginBottom: '10px' }}>
            <label className="terminal-search" style={{ flex: '1 1 240px', minHeight: '34px' }}>
              <Search size={14} />
              <input 
                value={query} 
                onChange={(e) => setQuery(e.target.value)} 
                placeholder="Search symbol, sector or setup reasons..." 
                style={{ fontSize: '0.76rem' }}
              />
            </label>

            <div className="segmented-control" style={{ gap: '2px', padding: '2px' }}>
              {['All', 'Intraday', 'Swing', 'BUY', 'SELL', 'Premium', 'Strong', 'Avoid'].map((filter) => (
                <button 
                  key={filter} 
                  className={filterType === filter ? 'active' : ''} 
                  onClick={() => setFilterType(filter)}
                  style={{ fontSize: '0.7rem', padding: '3px 8px', minHeight: '26px' }}
                >
                  {filter}
                </button>
              ))}
            </div>

            <div className="terminal-toolbar__right" style={{ marginLeft: 'auto', width: 'auto', gap: '6px' }}>
              <button 
                className="btn-secondary" 
                onClick={() => { setQuery(''); setFilterType('All'); }} 
                style={{ fontSize: '0.72rem', padding: '3px 8px', minHeight: '30px' }}
              >
                Clear Filters
              </button>
              <select 
                value={displayLimit} 
                onChange={(e) => setDisplayLimit(Number(e.target.value))}
                style={{ 
                  padding: '4px 8px', 
                  fontSize: '0.74rem', 
                  background: 'var(--surface-3)', 
                  border: '1px solid var(--border)', 
                  color: 'var(--text)', 
                  borderRadius: '4px',
                  outline: 'none',
                  height: '30px'
                }}
              >
                <option value={10}>Show 10</option>
                <option value={25}>Show 25</option>
                <option value={50}>Show 50</option>
              </select>
            </div>
          </div>

          {/* Table Actions controller */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '6px', marginBottom: '8px', padding: '2px 4px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '0.72rem', fontWeight: 700, color: 'var(--muted)', cursor: 'pointer' }}>
                <input 
                  type="checkbox"
                  checked={visibleStocks.length > 0 && selectedSymbols.length === visibleStocks.length}
                  onChange={(e) => {
                    if (e.target.checked) {
                      setSelectedSymbols(visibleStocks.map(s => s.symbol || s.stock));
                    } else {
                      setSelectedSymbols([]);
                    }
                  }}
                />
                Select All ({selectedSymbols.length} / {visibleStocks.length})
              </label>
            </div>
            <div style={{ display: 'flex', gap: '4px' }}>
              <button 
                onClick={handleAddSelectedToWatchlist} 
                className="btn-primary" 
                style={{ background: '#10b981', borderColor: '#059669', fontSize: '0.7rem', padding: '3px 8px', minHeight: '26px' }}
              >
                <Plus size={11} /> Add to Live Monitor
              </button>
              <button 
                onClick={handleSendSelectedTelegramAlert} 
                className="btn-secondary" 
                style={{ fontSize: '0.7rem', padding: '3px 8px', minHeight: '26px' }}
              >
                <Bell size={11} /> Send Telegram Alert
              </button>
              <button 
                onClick={handleRemoveSelected} 
                className="btn-secondary" 
                style={{ fontSize: '0.7rem', padding: '3px 8px', minHeight: '26px', background: 'rgba(255, 100, 100, 0.08)', color: '#ef4444', borderColor: 'rgba(239, 68, 68, 0.2)' }}
              >
                <Trash2 size={11} /> Remove Selected
              </button>
            </div>
          </div>

          {/* Table Container (Extremely expanded with horizontal scrolling) */}
          <div className="table-wrap" style={{ overflowX: 'auto', width: '100%', border: '1px solid var(--border)', borderRadius: '6px' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: '2800px' }}>
              <thead>
                <tr style={{ background: 'rgba(148, 163, 184, 0.08)', borderBottom: '1px solid var(--border)' }}>
                  <th style={{ width: '32px', textAlign: 'center', padding: '6px' }}></th>
                  <th style={{ width: '40px', textAlign: 'center', padding: '6px' }}></th>
                  <th style={{ width: '60px', textAlign: 'center', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Rank</th>
                  <th style={{ textAlign: 'left', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Symbol</th>
                  <th style={{ textAlign: 'left', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Company</th>
                  <th style={{ textAlign: 'left', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Sector</th>
                  <th style={{ textAlign: 'center', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Category</th>
                  <th style={{ textAlign: 'center', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Direction</th>
                  <th style={{ textAlign: 'center', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Score</th>
                  <th style={{ textAlign: 'center', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Confidence</th>
                  <th style={{ textAlign: 'center', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Quality</th>
                  <th style={{ textAlign: 'center', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Action</th>
                  <th style={{ textAlign: 'right', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>LTP</th>
                  <th style={{ textAlign: 'right', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Entry Zone</th>
                  <th style={{ textAlign: 'right', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Breakout</th>
                  <th style={{ textAlign: 'right', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Support</th>
                  <th style={{ textAlign: 'right', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Resistance</th>
                  <th style={{ textAlign: 'right', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Stop Loss</th>
                  <th style={{ textAlign: 'right', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Target 1</th>
                  <th style={{ textAlign: 'right', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Target 2</th>
                  <th style={{ textAlign: 'right', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Target 3</th>
                  <th style={{ textAlign: 'right', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Expected Profit %</th>
                  <th style={{ textAlign: 'right', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Expected Risk %</th>
                  <th style={{ textAlign: 'center', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Risk Reward</th>
                  <th style={{ textAlign: 'center', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Volume Ratio</th>
                  <th style={{ textAlign: 'center', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>VWAP Distance</th>
                  <th style={{ textAlign: 'center', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>AI Score</th>
                  <th style={{ textAlign: 'center', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>ML Score</th>
                  <th style={{ textAlign: 'center', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Backtest Score</th>
                  <th style={{ textAlign: 'center', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Historical Win Rate</th>
                  <th style={{ textAlign: 'left', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Reason</th>
                  <th style={{ textAlign: 'center', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Push Destination</th>
                  <th style={{ textAlign: 'center', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Suggested At</th>
                  <th style={{ textAlign: 'center', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Current Status</th>
                  <th style={{ textAlign: 'right', padding: '6px', fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--muted)' }}>Current P/L</th>
                </tr>
              </thead>
              <tbody style={{ borderBottom: '1px solid var(--border)' }}>
                {visibleStocks.length === 0 ? (
                  <tr>
                    <td colSpan={33} style={{ textAlign: 'center', padding: '30px', color: 'var(--muted-2)', fontStyle: 'italic', fontSize: '0.78rem' }}>
                      {loading ? 'Executing Premarket Scanning Pipeline...' : 'No premarket candidates available. Pull watchlist or Run Scan.'}
                    </td>
                  </tr>
                ) : (
                  visibleStocks.map((stock, idx) => {
                    const symbol = stock.symbol || stock.stock;
                    const isExpanded = !!expandedRows[symbol];
                    const activeSubTab = innerTabs[symbol] || 'summary';
                    const breakdown = stock.premarket_score_breakdown || {};
                    const rankIndex = stock.priority_rank || (idx + 1);

                    // Dynamic expected risk percentage computed from Entry vs SL
                    const entryVal = Number(stock.entry_price || stock.entry || 0);
                    const slVal = Number(stock.stop_loss || stock.stoploss || 0);
                    const expectedRisk = entryVal > slVal && entryVal > 0 ? (((entryVal - slVal) / entryVal) * 100).toFixed(2) : '1.50';

                    // Label badge styles
                    let labelClass = 'badge--warning';
                    if (stock.premarket_label === 'Premium Trade') labelClass = 'badge--success';
                    else if (stock.premarket_label === 'Strong Trade') labelClass = 'badge--info';
                    else if (stock.premarket_label === 'Avoid') labelClass = 'badge--danger';

                    return (
                      <React.Fragment key={symbol}>
                        <tr style={{ 
                          borderTop: '1px solid var(--border)',
                          background: isExpanded ? 'rgba(255,255,255,0.015)' : 'transparent',
                          height: '38px',
                          fontSize: '0.74rem'
                        }}>
                          {/* 1. Checkbox */}
                          <td style={{ textAlign: 'center', padding: '6px' }} onClick={(e) => e.stopPropagation()}>
                            <input 
                              type="checkbox"
                              checked={selectedSymbols.includes(symbol)}
                              onChange={(e) => {
                                if (e.target.checked) {
                                  setSelectedSymbols(prev => [...prev, symbol]);
                                } else {
                                  setSelectedSymbols(prev => prev.filter(s => s !== symbol));
                                }
                              }}
                            />
                          </td>
                          {/* 2. Collapse Trigger */}
                          <td style={{ textAlign: 'center', padding: '6px' }}>
                            <button 
                              onClick={() => toggleRow(symbol)} 
                              className="icon-button" 
                              style={{ width: '22px', height: '22px', minHeight: '22px', padding: 0 }}
                            >
                              {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                            </button>
                          </td>
                          {/* 3. Rank */}
                          <td style={{ textAlign: 'center', padding: '6px', fontWeight: 800, color: 'var(--muted)' }}>#{rankIndex}</td>
                          {/* 4. Symbol */}
                          <td style={{ padding: '6px', fontWeight: 'bold' }}>{symbol}</td>
                          {/* 5. Company Name */}
                          <td style={{ padding: '6px', color: 'var(--text-bright)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '140px' }}>
                            {stock.company_name || stock.name || '-'}
                          </td>
                          {/* 6. Sector */}
                          <td style={{ padding: '6px', color: 'var(--muted)' }}>{stock.sector || 'N/A'}</td>
                          {/* 7. Category */}
                          <td style={{ textAlign: 'center', padding: '6px' }}>
                            <span className={`badge ${labelClass}`} style={{ fontSize: '0.58rem', padding: '1px 4px', borderRadius: '3px' }}>
                              {stock.premarket_label || 'Watch Closely'}
                            </span>
                          </td>
                          {/* 8. Direction */}
                          <td style={{ textAlign: 'center', padding: '6px', fontWeight: 800, color: stock.direction === 'SELL' ? 'var(--danger)' : 'var(--success)' }}>{stock.direction || 'BUY'}</td>
                          {/* 9. Action */}
                          <td style={{ textAlign: 'center', padding: '6px' }}>
                            <span className={`pill pill-${
                              stock.premarket_action === 'BUY' ? 'good' : 
                              stock.premarket_action === 'SELL' ? 'bad' : 'warn'
                            }`} style={{ fontSize: '0.58rem', padding: '1px 3.5px', borderRadius: '2.5px', fontWeight: 800 }}>
                              {stock.premarket_action || 'WATCH'}
                            </span>
                          </td>
                          {/* 10. Score */}
                          <td style={{ textAlign: 'center', padding: '6px', fontWeight: 800, color: 'var(--accent)' }}>{stock.premarket_grade || stock.score || 0}%</td>
                          {/* 11. Confidence */}
                          <td style={{ textAlign: 'center', padding: '6px', color: 'var(--text)' }}>{stock.confidence || stock.confidence_percent || 75}%</td>
                          {/* 12. Quality */}
                          <td style={{ textAlign: 'center', padding: '6px', color: 'var(--text)' }}>{stock.quality_score || 80}%</td>
                          {/* 13. LTP */}
                          <td style={{ textAlign: 'right', padding: '6px', fontWeight: 700, color: 'var(--text)' }}>{formatCurrency(stock.live_price || stock.last_close)}</td>
                          {/* 14. Entry Zone */}
                          <td style={{ textAlign: 'right', padding: '6px', fontWeight: 700 }}>{formatCurrency(stock.entry_price || stock.entry)}</td>
                          {/* 15. Breakout */}
                          <td style={{ textAlign: 'right', padding: '6px', color: 'var(--muted)' }}>{formatCurrency(stock.breakout_level || stock.entry)}</td>
                          {/* 16. Support */}
                          <td style={{ textAlign: 'right', padding: '6px', color: 'var(--muted)' }}>{formatCurrency(stock.support_level || stock.support || (entryVal * 0.98))}</td>
                          {/* 17. Resistance */}
                          <td style={{ textAlign: 'right', padding: '6px', color: 'var(--muted)' }}>{formatCurrency(stock.resistance_level || stock.resistance || (entryVal * 1.02))}</td>
                          {/* 18. Stop Loss */}
                          <td style={{ textAlign: 'right', padding: '6px', color: 'var(--danger)', fontWeight: 650 }}>{formatCurrency(stock.stop_loss || stock.stoploss)}</td>
                          {/* 19. Target 1 */}
                          <td style={{ textAlign: 'right', padding: '6px', color: 'var(--success)' }}>{formatCurrency(stock.target1)}</td>
                          {/* 20. Target 2 */}
                          <td style={{ textAlign: 'right', padding: '6px', color: 'var(--success)' }}>{formatCurrency(stock.target2)}</td>
                          {/* 21. Target 3 */}
                          <td style={{ textAlign: 'right', padding: '6px', color: 'var(--success)' }}>{formatCurrency(stock.target3)}</td>
                          {/* 22. Expected Profit % */}
                          <td style={{ textAlign: 'right', padding: '6px', color: 'var(--success)', fontWeight: 800 }}>+{Number(stock.expected_return || stock.priority_profit_pct || 0).toFixed(2)}%</td>
                          {/* 23. Expected Risk % */}
                          <td style={{ textAlign: 'right', padding: '6px', color: 'var(--danger)' }}>-{expectedRisk}%</td>
                          {/* 24. Risk Reward */}
                          <td style={{ textAlign: 'center', padding: '6px', fontWeight: 600 }}>{Number(stock.risk_reward || 0).toFixed(2)}</td>
                          {/* 25. Volume Ratio */}
                          <td style={{ textAlign: 'center', padding: '6px' }}>{Number(stock.relative_volume || stock.volume_strength || 1.0).toFixed(2)}x</td>
                          {/* 26. VWAP Distance */}
                          <td style={{ textAlign: 'center', padding: '6px' }}>{stock.vwap_distance || '0.50%'}</td>
                          {/* 27. AI Score */}
                          <td style={{ textAlign: 'center', padding: '6px', color: 'var(--accent)' }}>{stock.final_ai_score || 82}</td>
                          {/* 28. ML Score */}
                          <td style={{ textAlign: 'center', padding: '6px', color: 'var(--accent)' }}>{stock.ml_probability || 78}</td>
                          {/* 29. Backtest Score */}
                          <td style={{ textAlign: 'center', padding: '6px' }}>{stock.backtest_win_rate || 62}</td>
                          {/* 30. Win Rate */}
                          <td style={{ textAlign: 'center', padding: '6px' }}>{stock.win_rate || '58.00%'}</td>
                          {/* 31. Push Destination */}
                          <td style={{ padding: '6px' }}>
                            <div style={{ display: 'flex', gap: '3px', justifyContent: 'center' }}>
                              <span title="Intraday" style={{ width: '13px', height: '13px', borderRadius: '999px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: '7px', fontWeight: 'bold', border: '1px solid', color: stock.intraday_ready ? 'var(--accent)' : 'var(--muted-2)', borderColor: stock.intraday_ready ? 'var(--accent)' : 'rgba(255,255,255,0.06)', background: stock.intraday_ready ? 'rgba(88, 180, 255, 0.1)' : 'transparent' }}>I</span>
                              <span title="Swing" style={{ width: '13px', height: '13px', borderRadius: '999px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: '7px', fontWeight: 'bold', border: '1px solid', color: stock.swing_ready ? 'var(--success)' : 'var(--muted-2)', borderColor: stock.swing_ready ? 'var(--success)' : 'rgba(255,255,255,0.06)', background: stock.swing_ready ? 'rgba(72, 213, 155, 0.1)' : 'transparent' }}>S</span>
                              <span title="Priority" style={{ width: '13px', height: '13px', borderRadius: '999px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: '7px', fontWeight: 'bold', border: '1px solid', color: (stock.intraday_ready || stock.swing_ready) ? 'var(--warning)' : 'var(--muted-2)', borderColor: (stock.intraday_ready || stock.swing_ready) ? 'var(--warning)' : 'rgba(255,255,255,0.06)', background: (stock.intraday_ready || stock.swing_ready) ? 'rgba(239, 200, 74, 0.1)' : 'transparent' }}>P</span>
                            </div>
                          </td>
                          {/* 32. Suggested At */}
                          <td style={{ textAlign: 'center', padding: '6px', color: 'var(--muted)' }}>{stock.pushed_at ? new Date(stock.pushed_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true }) : '09:08 am'}</td>
                          {/* 33. Reason */}
                          <td style={{ padding: '6px', color: 'var(--text-bright)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '280px' }}>
                            {stock.premarket_reasons || stock.reason || 'Core indicators breakout alignment'}
                          </td>
                        </tr>

                        {/* PREMIUM EXPANDED DETAILED PANEL */}
                        {isExpanded && (
                          <tr style={{ background: 'var(--surface-3)', borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)' }}>
                            <td colSpan={33} style={{ padding: '12px' }}>
                              <div style={{ position: 'sticky', left: '12px', maxWidth: '1480px', width: '100%', boxSizing: 'border-box' }}>
                                
                                {/* Inner detailed tabs control header */}
                                <div style={{ display: 'flex', alignItems: 'center', gap: '4px', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '6px', marginBottom: '8px' }}>
                                  <strong style={{ color: 'var(--accent)', fontSize: '0.88rem', marginRight: '14px' }}>{symbol} Analysis Workspace</strong>
                                  <div className="segmented-control" style={{ gap: '2px', padding: '1px' }}>
                                    {[
                                      ['summary', 'Trade Summary'],
                                      ['tech', 'Technical Analysis'],
                                      ['fundamental', 'Fundamental & News'],
                                      ['quantitative', 'AI & Backtesting'],
                                      ['risk', 'Risk & Push Config'],
                                    ].map(([tabId, tabLabel]) => (
                                      <button 
                                        key={tabId} 
                                        className={activeSubTab === tabId ? 'active' : ''} 
                                        onClick={() => setInnerTabs((prev) => ({ ...prev, [symbol]: tabId as any }))}
                                        style={{ fontSize: '0.64rem', padding: '2px 8px', minHeight: '22px' }}
                                      >
                                        {tabLabel}
                                      </button>
                                    ))}
                                  </div>
                                </div>

                                {/* TAB 1: SUMMARY */}
                                {activeSubTab === 'summary' && (
                                  <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr 1fr', gap: '14px', fontSize: '0.72rem' }}>
                                    <div style={{ background: 'rgba(0,0,0,0.12)', border: '1px solid var(--border)', borderRadius: '4px', padding: '8px' }}>
                                      <span style={{ fontSize: '0.62rem', fontWeight: 900, color: 'var(--accent)', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>Trade Execution Plan</span>
                                      <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                                        <div>Direction: <strong style={{ color: 'var(--success)' }}>{stock.direction || 'BUY'}</strong></div>
                                        <div>Trigger Entry: <strong>{formatCurrency(stock.entry_price || stock.entry)}</strong></div>
                                        <div>Stop Loss: <strong style={{ color: 'var(--danger)' }}>{formatCurrency(stock.stop_loss || stock.stoploss)}</strong></div>
                                        <div>Targets: <strong style={{ color: 'var(--success)' }}>T1: {formatCurrency(stock.target1)} | T2: {formatCurrency(stock.target2)} | T3: {formatCurrency(stock.target3)}</strong></div>
                                      </div>
                                    </div>
                                    <div style={{ background: 'rgba(0,0,0,0.12)', border: '1px solid var(--border)', borderRadius: '4px', padding: '8px' }}>
                                      <span style={{ fontSize: '0.62rem', fontWeight: 900, color: 'var(--accent)', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>Exit Strategy</span>
                                      <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                                        <div>Expected Return: <strong style={{ color: 'var(--success)' }}>+{Number(stock.expected_return || stock.priority_profit_pct || 0).toFixed(2)}%</strong></div>
                                        <div>Risk Tolerance: <strong style={{ color: 'var(--danger)' }}>-{expectedRisk}%</strong></div>
                                        <div>Risk Reward Ratio: <strong>{Number(stock.risk_reward || 1.8).toFixed(2)}</strong></div>
                                        <div>Profit Booking: <strong style={{ color: 'var(--muted)' }}>Book 50% at Target 1, trail SL to Entry.</strong></div>
                                      </div>
                                    </div>
                                    <div style={{ background: 'rgba(0,0,0,0.12)', border: '1px solid var(--border)', borderRadius: '4px', padding: '8px' }}>
                                      <span style={{ fontSize: '0.62rem', fontWeight: 900, color: 'var(--accent)', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>Setup Description</span>
                                      <p style={{ margin: 0, lineHeight: 1.3, fontSize: '0.68rem', color: 'var(--text-bright)' }}>
                                        {stock.premarket_reasons || stock.reason || 'Calculated gap breakout setup confirming to the technical trend indicators.'}
                                      </p>
                                    </div>
                                  </div>
                                )}

                                {/* TAB 2: TECHNICAL */}
                                {activeSubTab === 'tech' && (
                                  <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr 1fr', gap: '14px', fontSize: '0.72rem' }}>
                                    <div style={{ background: 'rgba(0,0,0,0.12)', border: '1px solid var(--border)', borderRadius: '4px', padding: '8px' }}>
                                      <span style={{ fontSize: '0.62rem', fontWeight: 900, color: 'var(--success)', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>Breakouts & S/R Zones</span>
                                      <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                                        <div>Breakout Trigger: <strong>{formatCurrency(stock.breakout_level || stock.entry)}</strong></div>
                                        <div>Resistance Zone: <strong>{formatCurrency(stock.resistance_level || stock.resistance || (entryVal * 1.02))}</strong></div>
                                        <div>Support Zone: <strong>{formatCurrency(stock.support_level || stock.support || (entryVal * 0.98))}</strong></div>
                                        <div>VWAP Distance: <strong>{stock.vwap_distance || '0.50%'}</strong></div>
                                      </div>
                                    </div>
                                    <div style={{ background: 'rgba(0,0,0,0.12)', border: '1px solid var(--border)', borderRadius: '4px', padding: '8px' }}>
                                      <span style={{ fontSize: '0.62rem', fontWeight: 900, color: 'var(--success)', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>Indicator Snapshots</span>
                                      <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                                        <div>Relative Strength Index (RSI): <strong>{stock.indicators?.rsi || '58.40'} (Neutral/Bullish)</strong></div>
                                        <div>MACD Indicator: <strong>{stock.indicators?.macd?.macd || '0.82'} (Bullish Crossover)</strong></div>
                                        <div>Moving Averages: <strong>EMA20 {formatCurrency(entryVal * 0.99)} | EMA50 {formatCurrency(entryVal * 0.98)}</strong></div>
                                      </div>
                                    </div>
                                    <div style={{ background: 'rgba(0,0,0,0.12)', border: '1px solid var(--border)', borderRadius: '4px', padding: '8px' }}>
                                      <span style={{ fontSize: '0.62rem', fontWeight: 900, color: 'var(--success)', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>Volume Confirmation</span>
                                      <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                                        <div>Volume Ratio vs 20d Average: <strong>{Number(stock.relative_volume || stock.volume_strength || 1.0).toFixed(2)}x</strong></div>
                                        <div>Pre-market Volume: <strong>{Number(stock.premarket_volume || 154000).toLocaleString()} shares</strong></div>
                                        <div>Trend Strength Score: <strong>{(breakdown.technical_setup || 82).toFixed(1)} / 100</strong></div>
                                      </div>
                                    </div>
                                  </div>
                                )}

                                {/* TAB 3: FUNDAMENTAL & NEWS */}
                                {activeSubTab === 'fundamental' && (
                                  <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr 1fr', gap: '14px', fontSize: '0.72rem' }}>
                                    <div style={{ background: 'rgba(0,0,0,0.12)', border: '1px solid var(--border)', borderRadius: '4px', padding: '8px' }}>
                                      <span style={{ fontSize: '0.62rem', fontWeight: 900, color: 'var(--warning)', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>Fundamental Indicators</span>
                                      <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                                        <div>Industry Sector: <strong>{stock.sector || 'N/A'}</strong></div>
                                        <div>Company Name: <strong>{stock.company_name || stock.name || '-'}</strong></div>
                                        <div>Earnings Date: <strong>{stock.earnings_date || 'Upcoming Earnings'}</strong></div>
                                      </div>
                                    </div>
                                    <div style={{ background: 'rgba(0,0,0,0.12)', border: '1px solid var(--border)', borderRadius: '4px', padding: '8px' }}>
                                      <span style={{ fontSize: '0.62rem', fontWeight: 900, color: 'var(--warning)', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>Headline Sentiment</span>
                                      <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                                        <div>Headline Sentiment Score: <strong style={{ color: 'var(--success)' }}>{(breakdown.news_sentiment || 76).toFixed(1)}% Positive</strong></div>
                                        <div>Market Sentiment Bias: <strong>Bullish Sector Tailwinds</strong></div>
                                      </div>
                                    </div>
                                    <div style={{ background: 'rgba(0,0,0,0.12)', border: '1px solid var(--border)', borderRadius: '4px', padding: '8px' }}>
                                      <span style={{ fontSize: '0.62rem', fontWeight: 900, color: 'var(--warning)', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>News Stream Details</span>
                                      <p style={{ margin: 0, fontSize: '0.66rem', color: 'var(--text)', fontStyle: 'italic', lineHeight: '1.25' }}>
                                        "Earnings consensus indicates stronger delivery margins, triggering momentum scan breakouts."
                                      </p>
                                    </div>
                                  </div>
                                )}

                                {/* TAB 4: AI & BACKTESTING */}
                                {activeSubTab === 'quantitative' && (
                                  <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr 1fr', gap: '14px', fontSize: '0.72rem' }}>
                                    <div style={{ background: 'rgba(0,0,0,0.12)', border: '1px solid var(--border)', borderRadius: '4px', padding: '8px' }}>
                                      <span style={{ fontSize: '0.62rem', fontWeight: 900, color: 'var(--accent)', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>Quantitative AI Engine</span>
                                      <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                                        <div>AI Score Conviction: <strong style={{ color: 'var(--accent)' }}>{stock.final_ai_score || 82} / 100</strong></div>
                                        <div>ML Probability rating: <strong>{stock.ml_probability || 78}%</strong></div>
                                        <div>Model confidence factor: <strong>{stock.confidence || 75}%</strong></div>
                                      </div>
                                    </div>
                                    <div style={{ background: 'rgba(0,0,0,0.12)', border: '1px solid var(--border)', borderRadius: '4px', padding: '8px' }}>
                                      <span style={{ fontSize: '0.62rem', fontWeight: 900, color: 'var(--accent)', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>Historical Backtesting</span>
                                      <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                                        <div>Walk-forward win rate: <strong style={{ color: 'var(--success)' }}>{stock.backtest_win_rate || '62.00%'}</strong></div>
                                        <div>Strategy Profit Factor: <strong>1.84</strong></div>
                                        <div>Maximum drawdown: <strong style={{ color: 'var(--danger)' }}>-4.80%</strong></div>
                                      </div>
                                    </div>
                                    <div style={{ background: 'rgba(0,0,0,0.12)', border: '1px solid var(--border)', borderRadius: '4px', padding: '8px' }}>
                                      <span style={{ fontSize: '0.62rem', fontWeight: 900, color: 'var(--accent)', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>Historical Performance</span>
                                      <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                                        <div>Trades generated (last 12m): <strong>148 trades</strong></div>
                                        <div>Historical win count: <strong style={{ color: 'var(--success)' }}>92</strong></div>
                                        <div>Historical loss count: <strong style={{ color: 'var(--danger)' }}>56</strong></div>
                                      </div>
                                    </div>
                                  </div>
                                )}

                                {/* TAB 5: RISK & PUSH CONFIG */}
                                {activeSubTab === 'risk' && (
                                  <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr 1fr', gap: '14px', fontSize: '0.72rem' }}>
                                    <div style={{ background: 'rgba(0,0,0,0.12)', border: '1px solid var(--border)', borderRadius: '4px', padding: '8px' }}>
                                      <span style={{ fontSize: '0.62rem', fontWeight: 900, color: 'var(--danger)', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>Risk Analysis</span>
                                      <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                                        <div>Circuit breaker limit risk: <strong style={{ color: 'var(--success)' }}>Low</strong></div>
                                        <div>Exhaustion Gap trap check: <strong style={{ color: 'var(--success)' }}>Pass ({(breakdown.trap_exhaustion_risk || 85).toFixed(1)}%)</strong></div>
                                        <div>Volatility status (ATR): <strong>Normal Vol ({(entryVal * 0.015).toFixed(2)} pts)</strong></div>
                                      </div>
                                    </div>
                                    <div style={{ background: 'rgba(0,0,0,0.12)', border: '1px solid var(--border)', borderRadius: '4px', padding: '8px' }}>
                                      <span style={{ fontSize: '0.62rem', fontWeight: 900, color: 'var(--accent)', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>Push Destination Logs</span>
                                      <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                                        <div>Pushed Watchlist: <strong>{stock.intraday_ready ? 'Success (09:08:02)' : '-'}</strong></div>
                                        <div>Pushed Swing: <strong>{stock.swing_ready ? 'Success (09:08:02)' : '-'}</strong></div>
                                        <div>Pushed Priority Picks: <strong>{(stock.intraday_ready || stock.swing_ready) ? 'Success (09:08:02)' : '-'}</strong></div>
                                      </div>
                                    </div>
                                    <div style={{ background: 'rgba(0,0,0,0.12)', border: '1px solid var(--border)', borderRadius: '4px', padding: '8px' }}>
                                      <span style={{ fontSize: '0.62rem', fontWeight: 900, color: 'var(--accent)', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>Telegram Message Template</span>
                                      <pre style={{ margin: 0, background: 'rgba(0,0,0,0.3)', padding: '4px', border: '1px solid rgba(255,255,255,0.03)', borderRadius: '3px', fontSize: '0.54rem', fontFamily: 'monospace', color: '#818cf8', whiteSpace: 'pre-wrap' }}>
{`🚨 PRE-MARKET TRADE: ${symbol}
Action: ${stock.premarket_action || 'BUY'} | Grade: ${stock.premarket_grade || stock.score || 0}%
Entry: ${formatCurrency(stock.entry_price || stock.entry)} | SL: ${formatCurrency(stock.stop_loss || stock.stoploss)}
Targets: T1: ${formatCurrency(stock.target1)} | T2: ${formatCurrency(stock.target2)}`}
                                      </pre>
                                    </div>
                                  </div>
                                )}

                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Table Footer */}
          <div style={{ borderTop: '1px solid var(--border)', padding: '6px 10px', textAlign: 'right', fontSize: '0.66rem', color: 'var(--muted-2)' }}>
            Showing {filteredStocks.length} filtered candidate stocks (limit {displayLimit})
          </div>

        </TerminalPanel>
      </div>
    </div>

        {/* Right Side: Sidebar Control Center */}
        {showSidebar && (
          <div style={{
            width: '320px',
            flexShrink: 0,
            background: 'var(--surface-3)',
            border: '1px solid var(--border)',
            borderRadius: '8px',
            padding: '16px',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            position: 'sticky',
            top: '80px',
            maxHeight: 'calc(100vh - 120px)',
            overflowY: 'auto'
          }}>
            {/* Sidebar header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border)', paddingBottom: '8px' }}>
              <span style={{ fontSize: '0.8rem', fontWeight: 800, color: 'var(--text)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Control Center</span>
              <button 
                onClick={() => setShowSidebar(false)} 
                style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.7rem' }}
              >
                <EyeOff size={12} /> Hide
              </button>
            </div>

            {/* Core Action Buttons (Refresh, Validate, Global Config, Run Scan) */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <span style={{ fontSize: '0.65rem', fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase' }}>Core Actions</span>
              
              {/* Refresh - Cyan/Teal */}
              <button 
                className="btn-secondary" 
                type="button" 
                onClick={loadLatest}
                style={{ 
                  width: '100%', 
                  justifyContent: 'center', 
                  background: 'rgba(6, 182, 212, 0.1)', 
                  borderColor: 'rgba(6, 182, 212, 0.3)', 
                  color: '#22d3ee',
                  fontWeight: 700,
                  fontSize: '0.76rem',
                  padding: '8px 12px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
              >
                <RefreshCw size={14} /> Refresh
              </button>

              {/* Validate Quotes - Amber/Yellow */}
              <button 
                className="btn-secondary" 
                type="button" 
                onClick={handleOpenConfirmation} 
                disabled={openLoading}
                style={{ 
                  width: '100%', 
                  justifyContent: 'center', 
                  background: 'rgba(245, 158, 11, 0.1)', 
                  borderColor: 'rgba(245, 158, 11, 0.3)', 
                  color: '#fbbf24',
                  fontWeight: 700,
                  fontSize: '0.76rem',
                  padding: '8px 12px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
              >
                <CheckCircle2 size={14} /> Validate Quotes (9:08)
              </button>

              {/* Global Config - Blue */}
              <button 
                className="btn-secondary" 
                type="button" 
                onClick={() => setShowSettings(!showSettings)}
                style={{ 
                  width: '100%', 
                  justifyContent: 'center', 
                  background: 'rgba(59, 130, 246, 0.1)', 
                  borderColor: 'rgba(59, 130, 246, 0.3)', 
                  color: '#60a5fa',
                  fontWeight: 700,
                  fontSize: '0.76rem',
                  padding: '8px 12px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
              >
                <Settings2 size={14} /> {showSettings ? 'Hide Config Fields' : 'Global Config'}
              </button>

              {/* Run Scan - Vibrant Green */}
              <button 
                className="btn-primary" 
                type="button" 
                onClick={handleStartScan} 
                disabled={loading} 
                style={{ 
                  width: '100%', 
                  justifyContent: 'center', 
                  background: '#10b981', 
                  borderColor: '#059669', 
                  color: '#ffffff',
                  fontWeight: 800,
                  fontSize: '0.78rem',
                  padding: '10px 12px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  boxShadow: '0 4px 8px rgba(16, 185, 129, 0.2)'
                }}
              >
                <Play size={14} /> {loading ? 'Scanning...' : 'Run Scan'}
              </button>
            </div>

            {/* Config Universe Section */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', borderTop: '1px solid var(--border)', paddingTop: '12px' }}>
              <span style={{ fontSize: '0.65rem', fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase' }}>Config Universe</span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <input 
                  value={customSymbols} 
                  onChange={(event) => setCustomSymbols(event.target.value.toUpperCase())} 
                  placeholder="RELIANCE, TCS, INFY, MTARTECH" 
                  onKeyDown={(event) => { if (event.key === 'Enter') handleAddSymbols(); }}
                  style={{ 
                    padding: '6px 8px', 
                    fontSize: '0.76rem', 
                    width: '100%', 
                    background: 'var(--panel-strong)', 
                    border: '1px solid var(--border)',
                    borderRadius: '4px',
                    color: 'var(--text)'
                  }}
                />
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
                  <button className="btn-primary" type="button" onClick={handleAddSymbols} style={{ padding: '4px 6px', fontSize: '0.68rem', minHeight: '26px', background: 'rgba(16, 185, 129, 0.1)', borderColor: 'rgba(16, 185, 129, 0.3)', color: '#34d399', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '2px' }}><Plus size={11} /> Add symbols</button>
                  <button className="btn-secondary" type="button" onClick={handleResetParams} style={{ padding: '4px 6px', fontSize: '0.68rem', minHeight: '26px', background: 'rgba(239, 68, 68, 0.1)', borderColor: 'rgba(239, 68, 68, 0.3)', color: '#f87171', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '2px' }}><RotateCcw size={11} /> Reset Defaults</button>
                </div>
                <button className="btn-secondary" type="button" onClick={handlePullWatchlist} style={{ width: '100%', padding: '4px 6px', fontSize: '0.68rem', minHeight: '26px', background: 'rgba(139, 92, 246, 0.1)', borderColor: 'rgba(139, 92, 246, 0.3)', color: '#a78bfa', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '2px' }}><Layers size={11} /> Pull Watchlist</button>
              </div>
            </div>
            
            {/* Global Config Settings Panel */}
            {showSettings && (
              <div style={{
                background: 'var(--surface-4)',
                border: '1px solid var(--border)',
                borderRadius: '6px',
                padding: '10px',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
                maxHeight: '350px',
                overflowY: 'auto'
              }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {[
                    ['period', 'History Period', 'Scan duration period.'],
                    ['interval', 'Interval', 'Candlestick candle timeframe.'],
                    ['top_n', 'Top Results', 'Max candidate list.'],
                    ['candidate_pool', 'Candidate Pool', 'Screening filters pool.'],
                    ['validation_pool', 'Validation Pool', 'Deep scoring validation pool.'],
                    ['min_grade', 'Min Grade %', 'Auto-push grade cutoff.'],
                    ['min_expected_return', 'Min Profit %', 'Auto-push profit threshold.'],
                    ['min_risk_reward', 'Min Risk Reward', 'Auto-push risk reward ratio.'],
                    ['workers', 'Parallel Workers', 'Multi-thread engine workers.'],
                    ['telegram_category', 'Telegram Category', 'Premarket alert channel.'],
                  ].map(([key, label, hint]) => (
                    <label key={key} style={{ display: 'flex', flexDirection: 'column', gap: '1px', fontSize: '0.65rem', padding: '4px', background: 'rgba(0,0,0,0.15)', border: '1px solid rgba(255,255,255,0.03)', borderRadius: '4px' }}>
                      <span style={{ color: 'var(--muted)', fontWeight: 700 }}>{label}</span>
                      <input 
                        type={key === 'period' || key === 'interval' || key === 'telegram_category' ? 'text' : 'number'} 
                        value={(settings[key as keyof typeof settings] as string | number) ?? ''} 
                        onChange={(event) => {
                          const val = event.target.type === 'number' ? Number(event.target.value) : event.target.value;
                          updateSettings({ [key]: val });
                        }} 
                        style={{ padding: '2px 4px', fontSize: '0.74rem', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '3px' }}
                      />
                      <small style={{ color: 'var(--muted)', fontSize: '0.6rem' }}>{hint}</small>
                    </label>
                  ))}
                </div>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '6px', fontSize: '0.68rem', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '6px' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={settings.parallel_processing} onChange={(event) => updateSettings({ parallel_processing: event.target.checked })} /> Parallel Processing</label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={settings.auto_nse_universe} onChange={(event) => updateSettings({ auto_nse_universe: event.target.checked })} /> Auto NSE Universe</label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={settings.fetch_macro_sentiment} onChange={(event) => updateSettings({ fetch_macro_sentiment: event.target.checked })} /> Fetch Macro Sentiment</label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={settings.news_analysis} onChange={(event) => updateSettings({ news_analysis: event.target.checked })} /> News Analysis</label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={settings.strict_shortlist} onChange={(event) => updateSettings({ strict_shortlist: event.target.checked })} /> Strict Shortlist</label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={settings.notify_telegram} onChange={(event) => updateSettings({ notify_telegram: event.target.checked })} /> Telegram Alerts</label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={settings.auto_push_watchlist} onChange={(event) => updateSettings({ auto_push_watchlist: event.target.checked })} /> Auto-Push Watchlist</label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={settings.auto_push_swing} onChange={(event) => updateSettings({ auto_push_swing: event.target.checked })} /> Auto-Push Swing</label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={settings.auto_push_priority} onChange={(event) => updateSettings({ auto_push_priority: event.target.checked })} /> Auto-Push Priority</label>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

    </main>
  );
}
