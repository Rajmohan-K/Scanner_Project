"use client";

import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Bot,
  IndianRupee,
  Layers,
  ListChecks,
  Octagon,
  Play,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  TrendingUp,
  Zap,
  Plus,
  Trash2,
  Sliders,
  SlidersHorizontal,
  BellRing
} from 'lucide-react';
import {
  getAlgoWatchlistStreamUrl,
  sendToAlgo,
  clearAlgoQueue,
  getAlgoWatchlistConfig,
  saveAlgoWatchlistConfig,
  getAlgoWatchlistSources,
  addAlgoCustomStock,
  deleteAlgoCustomStock,
  getAlgoWatchlistStatus,
  searchStocks,
  localStockSearch
} from '@/lib/api';
import { PageHero, TerminalPanel, DataTable, MetricTile } from '@/components/terminal/TerminalPrimitives';
import { useToast } from '@/components/layout/ToastProvider';

const money = (value: unknown) => Number(value || 0).toLocaleString('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 });
const percent = (value: unknown) => `${Number(value || 0).toFixed(2)}%`;
const number = (value: unknown, digits = 2) => Number(value || 0).toFixed(digits);

function getSearchDisplaySymbol(stock: any) {
  if (stock.exchange === 'BSE') return stock.bse_symbol || stock.symbol.replace(/\.BO$/, '');
  return stock.nse_symbol || stock.symbol.replace(/\.NS$/, '');
}

function AlgoStockDetailsPanel({ row, onClose }: { row: any; onClose: () => void }) {
  const fails = (row.rejection_reason || row.reason || "").toLowerCase();
  
  const checks = [
    { name: "1. Live Data Freshness", key: "stale", desc: "Quote age is fresh and within stale data limits" },
    { name: "2. Volume Confirmation", key: "volume", desc: "Trading volume ratio is >= 2x average volume" },
    { name: "3. VWAP Confirmation", key: "vwap", desc: "Price maintains position above VWAP for BUY setup" },
    { name: "4. ADX Trend Strength", key: "adx", desc: "Trend strength indicator ADX is >= 20.0" },
    { name: "5. Breakout Quality", key: "breakout quality", desc: "Breakout score meets required threshold" },
    { name: "6. Breakout Level Proximity", key: "breakout level", desc: "Price is within 3% range of support/breakout line" },
    { name: "7. Risk/Reward Ratio", key: "risk/reward", desc: "Reward vs Risk ratio satisfies minimum target threshold" },
    { name: "8. Stoploss Width Tightness", key: "stoploss", desc: "Stoploss width is within max limit" },
    { name: "9. Target Realism", key: "target profit", desc: "Profit potential is realistically between 1.5% and 15%" },
    { name: "10. Liquidity Confirmation", key: "liquidity", desc: "Stock has solid average daily trading volume >= 10k" },
    { name: "11. Spread Slippage Shield", key: "spread slippage", desc: "Bid/Ask spread gap is narrow and <= 0.25%" },
    { name: "12. Momentum RSI Filter", key: "rsi", desc: "RSI confirms strong momentum (> 50 for BUY)" },
    { name: "13. Candle Confirmation", key: "candle", desc: "Bullish/bearish candle color confirms trend direction" },
    { name: "14. Already-Moved Protection", key: "moved too much", desc: "Stock has not already run up past safe entry limit" },
    { name: "15. False Breakout Reversal", key: "false-breakout", desc: "No immediate false breakout reversals detected" },
    { name: "16. Nifty Index Backdrop", key: "nifty", desc: "Broad market direction confirms background strength" },
    { name: "17. Sector Index Support", key: "sector", desc: "Sectoral index relative strength confirms stock selection" },
    { name: "18. Opening Gap Protection", key: "gap", desc: "Open to prev close gap is moderate and <= 1.5%" },
    { name: "19. Event & News Shield", key: "earnings", desc: "No immediate earnings releases or news risk scheduled" }
  ];

  return (
    <tr onClick={(e) => e.stopPropagation()}>
      <td colSpan={13} style={{ padding: 0 }}>
        <div 
          style={{
            background: 'rgba(10, 20, 35, 0.98)',
            borderTop: '2px solid var(--primary)',
            borderBottom: '2px solid var(--primary)',
            padding: '16px',
            color: 'var(--text)',
            boxSizing: 'border-box',
            width: '100%',
            textAlign: 'left'
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: '8px', marginBottom: '12px' }}>
            <h4 style={{ margin: 0, fontSize: '0.85rem', color: 'var(--primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>🔍 Risk Audit & Scoring Details: <strong>{row.symbol}</strong> ({row.company_name})</span>
            </h4>
            <button
              className="btn-secondary"
              onClick={onClose}
              style={{ padding: '2px 6px', fontSize: '0.66rem', minHeight: '20px' }}
            >
              Hide Details
            </button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
            {/* Indicators and Scores */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <h5 style={{ margin: '0 0 4px 0', fontSize: '0.76rem', color: 'var(--accent)', textTransform: 'uppercase' }}>Scores & Factors</h5>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', fontSize: '0.72rem' }}>
                <div>Technical Score: <strong>{number(row.tech_score || 0, 1)}/100</strong></div>
                <div>Volume Score: <strong>{number(row.vol_score || 0, 1)}/100</strong></div>
                <div>Momentum Score: <strong>{number(row.mom_score || 0, 1)}/100</strong></div>
                <div>Risk Score: <strong>{number(row.risk_score || 0, 1)}/100</strong></div>
                <div>Liquidity Score: <strong>{number(row.liq_score || 0, 1)}/100</strong></div>
                <div>Trend Score: <strong>{number(row.trend_score || 0, 1)}/100</strong></div>
                <div>Safety Score: <strong>{number(row.safety_score || 0, 1)}/100</strong></div>
                <div>ML Prob Score: <strong>{percent(row.ml_probability || 0)}</strong></div>
                <div style={{ gridColumn: '1 / -1', borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '6px', marginTop: '4px' }}>
                  Final Weighted Algo Score: <strong style={{ color: 'var(--primary)', fontSize: '0.85rem' }}>{number(row.algo_score || 0, 2)}</strong>
                </div>
              </div>
              
              <div style={{ marginTop: '8px', padding: '8px', background: 'rgba(255,255,255,0.02)', borderRadius: '4px', fontSize: '0.7rem' }}>
                <span style={{ color: 'var(--muted)', display: 'block', marginBottom: '2px' }}>AI/ML Justification Reason:</span>
                <span style={{ color: 'var(--text-light)', lineHeight: '1.4' }}>{row.ai_reason || row.reason || "None"}</span>
              </div>
            </div>

            {/* 19-point checkpoints audit log */}
            <div style={{ gridColumn: 'span 2' }}>
              <h5 style={{ margin: '0 0 6px 0', fontSize: '0.76rem', color: 'var(--accent)', textTransform: 'uppercase' }}>19-Point Quant Risk Gates Verification</h5>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 12px', maxHeight: '250px', overflowY: 'auto', paddingRight: '4px' }}>
                {checks.map((chk) => {
                  const failed = fails.includes(chk.key.toLowerCase());
                  return (
                    <div key={chk.key} style={{ display: 'flex', alignItems: 'flex-start', gap: '6px', fontSize: '0.68rem', padding: '3px 6px', background: failed ? 'rgba(239, 68, 68, 0.05)' : 'rgba(16, 185, 129, 0.05)', border: `1px solid ${failed ? 'rgba(239, 68, 68, 0.12)' : 'rgba(16, 185, 129, 0.12)'}`, borderRadius: '4px' }}>
                      <span style={{ color: failed ? 'var(--negative)' : 'var(--positive)', fontWeight: 'bold' }}>{failed ? '✗' : '✓'}</span>
                      <div>
                        <strong style={{ display: 'block', color: failed ? 'var(--negative)' : 'var(--positive)' }}>{chk.name}</strong>
                        <span style={{ color: 'var(--muted)', fontSize: '0.62rem' }}>{chk.desc}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </td>
    </tr>
  );
}

export default function AlgoWatchlistPage() {
  const toast = useToast();
  
  // Connection states
  const [connection, setConnection] = useState<'Connecting' | 'Live' | 'Reconnecting' | 'Failed'>('Connecting');
  const [lastTick, setLastTick] = useState<string>('-');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  // Data streams
  const [signals, setSignals] = useState<any[]>([]);
  const [rejections, setRejections] = useState<any[]>([]);
  const [highProfitable, setHighProfitable] = useState<any[]>([]);
  const [eligible, setEligible] = useState<any[]>([]);
  const [queue, setQueue] = useState<any[]>([]);
  const [customStocks, setCustomStocks] = useState<any[]>([]);
  const [algoStatus, setAlgoStatus] = useState<any>(null);

  // Configuration Panel
  const [config, setConfig] = useState<Record<string, string>>({});
  const [showConfig, setShowConfig] = useState(false);
  const [showSourcingChannels, setShowSourcingChannels] = useState(false);
  const [sources, setSources] = useState<any[]>([]);

  // Input states
  const [customSymbol, setCustomSymbol] = useState('');
  const lastStreamUpdateRef = useRef<number>(Date.now());

  // Click-to-expand selected symbol details state
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);

  // Autocomplete suggestions state
  const [stockSuggestions, setStockSuggestions] = useState<any[]>([]);
  const [showStockSuggestions, setShowStockSuggestions] = useState(false);
  const [stockSuggestionsLoading, setStockSuggestionsLoading] = useState(false);

  // Top ranked suggestion (highest selection score)
  const topRanked = useMemo(() => {
    if (!highProfitable.length) return null;
    return [...highProfitable].sort((a, b) => b.algo_score - a.algo_score)[0];
  }, [highProfitable]);

  // Autocomplete search token effect
  useEffect(() => {
    const activeToken = customSymbol.trim();
    if (!activeToken || !showStockSuggestions) {
      setStockSuggestions([]);
      return;
    }
    let cancelled = false;
    const localResults = localStockSearch(activeToken, 8);
    setStockSuggestions(localResults);
    setStockSuggestionsLoading(true);
    searchStocks(activeToken, 8)
      .then((payload) => {
        if (!cancelled) {
          const apiResults = payload.results || [];
          const merged = [...apiResults];
          for (const fallback of localResults) {
            if (!merged.some((stock) => stock.symbol === fallback.symbol)) merged.push(fallback);
          }
          setStockSuggestions(merged.slice(0, 8));
        }
      })
      .catch(() => {
        if (!cancelled) setStockSuggestions(localResults);
      })
      .finally(() => {
        if (!cancelled) setStockSuggestionsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [customSymbol, showStockSuggestions]);

  // Load static configurations and sources
  async function loadData() {
    try {
      const configRes = await getAlgoWatchlistConfig();
      if (configRes.status === 'ok') {
        setConfig(configRes.config || {});
      }
      const sourcesRes = await getAlgoWatchlistSources();
      if (sourcesRes.status === 'ok') {
        setSources(sourcesRes.sources || []);
      }
    } catch (err: any) {
      console.error('Failed to load initial config / sources', err);
    }
  }

  // Connect SSE
  useEffect(() => {
    loadData();

    let source: EventSource | null = null;
    let fallbackInterval: number | null = null;

    function connectSSE() {
      if (source) source.close();
      
      source = new EventSource(getAlgoWatchlistStreamUrl());
      source.onopen = () => {
        setConnection('Live');
        setLoading(false);
      };
      
      source.onerror = () => {
        setConnection('Reconnecting');
      };

      source.addEventListener('ALGO_WATCHLIST_UPDATED', (event) => {
        try {
          const payload = JSON.parse((event as MessageEvent).data);
          lastStreamUpdateRef.current = Date.now();
          setSignals(payload.signals || []);
          setRejections(payload.rejections || []);
          setHighProfitable(payload.high_profitable || []);
          setEligible(payload.eligible || []);
          setQueue(payload.queue || []);
          setCustomStocks(payload.custom_stocks || []);
          setAlgoStatus(payload.algo_status || null);
          if (payload.algo_config) {
            setConfig(payload.algo_config);
          }
          setLastTick(payload.updated_at || new Date().toLocaleTimeString('en-IN'));
          setConnection('Live');
          setLoading(false);
        } catch (err) {
          console.error('Error parsing SSE payload', err);
        }
      });
    }

    connectSSE();

    fallbackInterval = window.setInterval(() => {
      if (Date.now() - lastStreamUpdateRef.current > 7000) {
        setConnection('Reconnecting');
        connectSSE();
      }
    }, 5000);

    return () => {
      if (source) source.close();
      if (fallbackInterval) window.clearInterval(fallbackInterval);
    };
  }, []);

  // Save Config parameters
  async function handleSaveConfig(updates: Record<string, string>) {
    const nextConfig = { ...config, ...updates };
    setConfig(nextConfig);
    try {
      const response = await saveAlgoWatchlistConfig(updates);
      if (response.status === 'ok') {
        toast?.push('ALGO parameters synced successfully.', 'success');
        // Refresh sources labels count
        const sourcesRes = await getAlgoWatchlistSources();
        if (sourcesRes.status === 'ok') setSources(sourcesRes.sources);
      }
    } catch (err: any) {
      toast?.push(err?.message || 'Failed to save config parameters', 'error');
    }
  }

  // Add custom symbol watch
  async function handleAddCustomStock() {
    if (!customSymbol.trim()) return;
    setBusy(true);
    try {
      const response = await addAlgoCustomStock(customSymbol);
      if (response.status === 'ok') {
        toast?.push(`Added ${response.symbol} to ALGO Watchlist monitoring.`, 'success');
        setCustomSymbol('');
        loadData();
      } else {
        toast?.push(response.message || 'Error adding symbol', 'error');
      }
    } catch (err: any) {
      toast?.push(err?.response?.data?.message || err?.message || 'Error resolving symbol', 'error');
    } finally {
      setBusy(false);
    }
  }

  // Remove custom symbol watch
  async function handleRemoveCustomStock(symbol: string) {
    setBusy(true);
    try {
      const response = await deleteAlgoCustomStock(symbol);
      if (response.status === 'ok') {
        toast?.push(`Removed ${symbol} from monitoring.`, 'warning');
        loadData();
      }
    } catch (err: any) {
      toast?.push(err?.message || 'Error removing symbol', 'error');
    } finally {
      setBusy(false);
    }
  }

  // Send single symbol to queue
  async function triggerSendToAlgo(symbol: string) {
    setBusy(true);
    try {
      const response = await sendToAlgo(symbol);
      if (response.status === 'ok') {
        toast?.push(`Queued ${symbol} for automated execution.`, 'success');
      } else {
        toast?.push(response.message || `Failed to queue ${symbol}`, 'error');
      }
    } catch (err: any) {
      toast?.push(err?.response?.data?.message || err?.message || 'Error processing request', 'error');
    } finally {
      setBusy(false);
    }
  }

  // Send top ranked signal
  async function sendTopTrade() {
    if (!topRanked) {
      toast?.push('No qualified high-profitable setups available currently.', 'warning');
      return;
    }
    await triggerSendToAlgo(topRanked.symbol);
  }

  // Emergency stop and clear queue
  async function triggerClearAlgoQueue() {
    setBusy(true);
    try {
      const response = await clearAlgoQueue();
      toast?.push(response.message || 'Execution queue cancelled successfully.', 'warning');
    } catch (err: any) {
      toast?.push(err?.response?.data?.message || err?.message || 'Failed to clear queue', 'error');
    } finally {
      setBusy(false);
    }
  }

  const queueRows = queue.map((row, index) => [
    `#${index + 1}`,
    <strong key="sym">{row.symbol}</strong>,
    <span key="side" className={`status-pill ${row.side === 'BUY' ? 'positive' : 'negative'}`}>{row.side}</span>,
    money(row.entry_price),
    money(row.stop_loss),
    money(row.target),
    row.quantity,
    money(row.capital_allocation),
    percent(row.confidence),
    number(row.algo_score),
    <span key="status" className={`status-pill ${row.execution_status === 'EXECUTED' ? 'positive' : row.execution_status === 'PENDING' ? 'warn' : 'negative'}`}>{row.execution_status}</span>,
    <span key="sent" className="status-pill">{row.sent_to_algo}</span>
  ]);

  const customStocksRows = customStocks.map((row) => [
    <strong key="sym">{row.symbol}</strong>,
    <span key="name" className="text-muted">{row.company_name}</span>,
    row.source || 'custom',
    <span key="status" className="status-pill positive">{row.monitoring_status}</span>,
    <button
      key="action"
      className="btn-secondary text-danger"
      type="button"
      disabled={busy}
      onClick={() => handleRemoveCustomStock(row.symbol)}
      style={{ padding: '2px 6px', minHeight: '22px' }}
    >
      <Trash2 size={12} /> Remove
    </button>
  ]);

  // Custom table row clicking wrapper to display details
  function getCustomSignalsTable(data: any[]) {
    const headers = ['Symbol', 'Company', 'Side', 'Signal Type', 'Entry', 'Current Price', 'Stoploss', 'Target 1', 'ML Prob', 'Algo Score', 'Risk/Reward', 'Auto Trade', 'Signal Justification'];
    return (
      <div className="terminal-table" style={{ overflowX: 'auto', width: '100%' }}>
        <div className="terminal-table-head" style={{ display: 'grid', gridTemplateColumns: '90px 140px 60px 100px 80px 80px 80px 80px 70px 80px 80px 80px 1fr', minWidth: '1100px' }}>
          {headers.map((h, i) => <span key={i}>{h}</span>)}
        </div>
        <div style={{ minWidth: '1100px' }}>
          {data.length === 0 ? (
            <div style={{ padding: '24px', textAlign: 'center', color: 'var(--muted)' }}>No active watchlist signals.</div>
          ) : (
            data.map((row) => {
              const isSelected = selectedSymbol === row.symbol;
              return (
                <React.Fragment key={row.symbol}>
                  <div 
                    className={`terminal-table-row ${isSelected ? 'is-selected' : ''}`}
                    onClick={() => setSelectedSymbol(isSelected ? null : row.symbol)}
                    style={{ display: 'grid', gridTemplateColumns: '90px 140px 60px 100px 80px 80px 80px 80px 70px 80px 80px 80px 1fr', cursor: 'pointer' }}
                  >
                    <strong>{row.symbol}</strong>
                    <span className="text-muted" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{row.company_name}</span>
                    <span className={`status-pill ${row.side === 'BUY' ? 'positive' : 'negative'}`}>{row.side}</span>
                    <span>{row.signal_type || 'Momentum'}</span>
                    <span>{money(row.entry_price)}</span>
                    <span>{money(row.current_price)}</span>
                    <span>{money(row.stop_loss)}</span>
                    <span>{money(row.target_1)}</span>
                    <span>{percent(row.ml_probability)}</span>
                    <strong>{number(row.algo_score)}</strong>
                    <span>{number(row.risk_reward)}x</span>
                    <span className={`status-pill ${row.auto_trade_allowed === 'YES' ? 'positive' : 'warn'}`}>{row.auto_trade_allowed}</span>
                    <span className="text-muted" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontSize: '0.74rem' }}>{row.ai_reason || row.reason}</span>
                  </div>
                  {isSelected && <AlgoStockDetailsPanel row={row} onClose={() => setSelectedSymbol(null)} />}
                </React.Fragment>
              );
            })
          )}
        </div>
      </div>
    );
  }

  function getCustomProfitableTable(data: any[]) {
    const headers = ['Symbol', 'Company', 'Side', 'Entry', 'Current Price', 'Stoploss', 'Target 1', 'ML Prob', 'Algo Score', 'Risk/Reward', 'Action'];
    return (
      <div className="terminal-table" style={{ overflowX: 'auto', width: '100%' }}>
        <div className="terminal-table-head" style={{ display: 'grid', gridTemplateColumns: '120px 150px 70px 90px 90px 90px 90px 80px 90px 90px 1fr', minWidth: '1000px' }}>
          {headers.map((h, i) => <span key={i}>{h}</span>)}
        </div>
        <div style={{ minWidth: '1000px' }}>
          {data.length === 0 ? (
            <div style={{ padding: '24px', textAlign: 'center', color: 'var(--muted)' }}>No suggestions available. Check sourcing options.</div>
          ) : (
            data.map((row) => {
              const isSelected = selectedSymbol === row.symbol;
              const isTop = topRanked && topRanked.symbol === row.symbol;
              return (
                <React.Fragment key={row.symbol}>
                  <div 
                    className={`terminal-table-row ${isSelected ? 'is-selected' : ''}`}
                    onClick={() => setSelectedSymbol(isSelected ? null : row.symbol)}
                    style={{ display: 'grid', gridTemplateColumns: '120px 150px 70px 90px 90px 90px 90px 80px 90px 90px 1fr', cursor: 'pointer' }}
                  >
                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <strong>{row.symbol}</strong>
                      {isTop && <span className="algo-chip is-live" style={{ fontSize: '0.55rem', padding: '1px 3px' }}>TOP</span>}
                    </span>
                    <span className="text-muted" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{row.company_name}</span>
                    <span className={`status-pill ${row.side === 'BUY' ? 'positive' : 'negative'}`}>{row.side}</span>
                    <span>{money(row.entry_price)}</span>
                    <span>{money(row.current_price)}</span>
                    <span>{money(row.stop_loss)}</span>
                    <span>{money(row.target_1)}</span>
                    <span>{percent(row.ml_probability)}</span>
                    <strong>{number(row.algo_score)}</strong>
                    <span>{number(row.risk_reward)}x</span>
                    <button
                      className="btn-primary"
                      type="button"
                      disabled={busy || algoStatus?.status !== 'RUNNING'}
                      onClick={(e) => {
                        e.stopPropagation();
                        triggerSendToAlgo(row.symbol);
                      }}
                      style={{ padding: '2px 6px', fontSize: '0.68rem', minHeight: '20px' }}
                    >
                      <Play size={10} /> Send to Algo
                    </button>
                  </div>
                  {isSelected && <AlgoStockDetailsPanel row={row} onClose={() => setSelectedSymbol(null)} />}
                </React.Fragment>
              );
            })
          )}
        </div>
      </div>
    );
  }

  function getCustomEligibleTable(data: any[]) {
    const headers = ['Symbol', 'Company', 'Eligible', 'Capital Req.', 'Suggested Qty', 'Max Risk', 'Expected Profit', 'Entry Trigger', 'Auto-Trade Allowed', 'Eligibility Reason'];
    return (
      <div className="terminal-table" style={{ overflowX: 'auto', width: '100%' }}>
        <div className="terminal-table-head" style={{ display: 'grid', gridTemplateColumns: '100px 150px 80px 100px 100px 100px 110px 100px 120px 1fr', minWidth: '1050px' }}>
          {headers.map((h, i) => <span key={i}>{h}</span>)}
        </div>
        <div style={{ minWidth: '1050px' }}>
          {data.length === 0 ? (
            <div style={{ padding: '24px', textAlign: 'center', color: 'var(--muted)' }}>No eligible sized trades.</div>
          ) : (
            data.map((row) => {
              const isSelected = selectedSymbol === row.symbol;
              const matchingSignal = signals.find((s) => s.symbol === row.symbol) || row;
              return (
                <React.Fragment key={row.symbol}>
                  <div 
                    className={`terminal-table-row ${isSelected ? 'is-selected' : ''}`}
                    onClick={() => setSelectedSymbol(isSelected ? null : row.symbol)}
                    style={{ display: 'grid', gridTemplateColumns: '100px 150px 80px 100px 100px 100px 110px 100px 120px 1fr', cursor: 'pointer' }}
                  >
                    <strong>{row.symbol}</strong>
                    <span className="text-muted" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{row.company_name}</span>
                    <span className="status-pill positive">{row.algo_eligibility}</span>
                    <span>{money(row.capital_required)}</span>
                    <span>{row.suggested_quantity}</span>
                    <span className="negative">{money(row.max_risk)}</span>
                    <span className="positive">{money(row.expected_profit)}</span>
                    <span>{money(row.entry_trigger)}</span>
                    <span className={`status-pill ${row.auto_trade_allowed === 'YES' ? 'positive' : 'warn'}`}>{row.auto_trade_allowed}</span>
                    <span className="text-muted" style={{ fontSize: '0.74rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{row.eligible_reason}</span>
                  </div>
                  {isSelected && <AlgoStockDetailsPanel row={matchingSignal} onClose={() => setSelectedSymbol(null)} />}
                </React.Fragment>
              );
            })
          )}
        </div>
      </div>
    );
  }

  function getCustomRejectedTable(data: any[]) {
    const headers = ['Symbol', 'Company', 'Confidence', 'Volume Ratio', 'Risk/Reward', 'Already Moved', 'Avoid Reason'];
    return (
      <div className="terminal-table" style={{ overflowX: 'auto', width: '100%' }}>
        <div className="terminal-table-head" style={{ display: 'grid', gridTemplateColumns: '100px 150px 90px 95px 95px 100px 1fr', minWidth: '850px' }}>
          {headers.map((h, i) => <span key={i}>{h}</span>)}
        </div>
        <div style={{ minWidth: '850px' }}>
          {data.length === 0 ? (
            <div style={{ padding: '24px', textAlign: 'center', color: 'var(--muted)' }}>No rejected/avoided records.</div>
          ) : (
            data.map((row) => {
              const isSelected = selectedSymbol === row.symbol;
              return (
                <React.Fragment key={row.symbol}>
                  <div 
                    className={`terminal-table-row ${isSelected ? 'is-selected' : ''}`}
                    onClick={() => setSelectedSymbol(isSelected ? null : row.symbol)}
                    style={{ display: 'grid', gridTemplateColumns: '100px 150px 90px 95px 95px 100px 1fr', cursor: 'pointer' }}
                  >
                    <strong>{row.symbol}</strong>
                    <span className="text-muted" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{row.company_name}</span>
                    <span>{percent(row.confidence)}</span>
                    <span>{number(row.volume_ratio)}x</span>
                    <span>{number(row.risk_reward)}x</span>
                    <span>{percent(row.already_moved)}</span>
                    <span className="negative" style={{ fontSize: '0.74rem', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{row.reason}</span>
                  </div>
                  {isSelected && <AlgoStockDetailsPanel row={row} onClose={() => setSelectedSymbol(null)} />}
                </React.Fragment>
              );
            })
          )}
        </div>
      </div>
    );
  }

  // Algo session metrics
  const sessionStatus = algoStatus?.status || 'IDLE';
  const capitalAllocated = algoStatus?.portfolio?.capital_allocated || 100000;
  const netPnL = algoStatus?.portfolio?.net_pnl || 0;
  const maxTradesLimit = algoStatus?.session?.max_trades || 3;
  const maxLossLimit = algoStatus?.session?.max_loss || 2000;

  return (
    <main className="algo-page" style={{ paddingBottom: '30px' }}>
      <PageHero
        eyebrow="Strict Risk Qualification & Sizing"
        title="ALGO Watchlist Monitor"
        description="Centralized quantitative analysis bridge with 19-point filtering gates and AI/ML scoring. Prepares eligible candidates and dispatches strictly to the execution console."
        actions={<>
          <button className="btn-secondary" type="button" onClick={() => setShowConfig(!showConfig)} style={{ padding: '4px 8px', fontSize: '0.74rem', minHeight: '26px' }}><Sliders size={12} /> {showConfig ? 'Hide Settings' : 'Algo Settings'}</button>
          <button className="btn-secondary" type="button" onClick={sendTopTrade} disabled={busy || !topRanked || sessionStatus !== 'RUNNING'} style={{ padding: '4px 8px', fontSize: '0.74rem', minHeight: '26px' }}><Zap size={12} /> Send Top Trade</button>
          <button className="btn-danger" type="button" onClick={triggerClearAlgoQueue} disabled={busy} style={{ padding: '4px 8px', fontSize: '0.74rem', minHeight: '26px' }}><Octagon size={12} /> Clear Algo Queue</button>
        </>}
        metrics={[
          { label: 'Signal Source', value: 'ALGO WATCHLIST', tone: 'info' },
          { label: 'Paper Mode', value: config.paper_mode || 'ON', tone: config.paper_mode === 'ON' ? 'good' : 'warn' },
          { label: 'Real Trading', value: config.real_trading || 'OFF', tone: config.real_trading === 'ON' ? 'good' : 'warn' },
          { label: 'Stream', value: connection, tone: connection === 'Live' ? 'good' : 'warn' },
          { label: 'Tick Time', value: lastTick }
        ]}
      />

      {/* Settings Panel (Collapsed by default) */}
      {showConfig && (
        <div style={{
          background: 'var(--surface-3)',
          border: '1px solid var(--border)',
          borderRadius: '6px',
          padding: '12px',
          margin: '0 16px 14px 16px'
        }}>
          <h4 style={{ margin: '0 0 10px 0', fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--accent)' }}><Sliders size={12} style={{ marginRight: '4px' }} /> Configuration Parameters (Safe Defaults)</h4>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '8px' }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '0.66rem' }}>
              <span>Paper Trade Mode</span>
              <select value={config.paper_mode || 'ON'} onChange={(e) => handleSaveConfig({ paper_mode: e.target.value })} style={{ padding: '3px 6px', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '4px' }}>
                <option value="ON">ON (Paper Mode)</option>
                <option value="OFF">OFF</option>
              </select>
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '0.66rem' }}>
              <span>Real Live execution</span>
              <select value={config.real_trading || 'OFF'} onChange={(e) => handleSaveConfig({ real_trading: e.target.value })} style={{ padding: '3px 6px', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '4px' }}>
                <option value="OFF">OFF (Locked)</option>
                <option value="ON">ON (CAUTION)</option>
              </select>
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '0.66rem' }}>
              <span>Minimum Confidence %</span>
              <input type="number" min={50} max={100} value={config.min_confidence || '85'} onChange={(e) => handleSaveConfig({ min_confidence: e.target.value })} style={{ padding: '3px 6px', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '4px' }} />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '0.66rem' }}>
              <span>Minimum Algo Score</span>
              <input type="number" min={50} max={100} value={config.min_algo_score || '80'} onChange={(e) => handleSaveConfig({ min_algo_score: e.target.value })} style={{ padding: '3px 6px', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '4px' }} />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '0.66rem' }}>
              <span>Minimum Expected Profit %</span>
              <input type="number" step={0.1} value={config.min_expected_profit_pct || '1.5'} onChange={(e) => handleSaveConfig({ min_expected_profit_pct: e.target.value })} style={{ padding: '3px 6px', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '4px' }} />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '0.66rem' }}>
              <span>Minimum Risk/Reward</span>
              <input type="number" step={0.1} value={config.min_risk_reward || '2.0'} onChange={(e) => handleSaveConfig({ min_risk_reward: e.target.value })} style={{ padding: '3px 6px', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '4px' }} />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '0.66rem' }}>
              <span>Maximum Stoploss %</span>
              <input type="number" step={0.1} value={config.max_stoploss_pct || '1.5'} onChange={(e) => handleSaveConfig({ max_stoploss_pct: e.target.value })} style={{ padding: '3px 6px', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '4px' }} />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '0.66rem' }}>
              <span>Volume Spike Multiplier</span>
              <input type="number" step={0.1} value={config.volume_multiplier || '2.0'} onChange={(e) => handleSaveConfig({ volume_multiplier: e.target.value })} style={{ padding: '3px 6px', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '4px' }} />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '0.66rem' }}>
              <span>Stale Quote Max Age (seconds)</span>
              <input type="number" step={0.1} value={config.stale_data_max_age || '2.0'} onChange={(e) => handleSaveConfig({ stale_data_max_age: e.target.value })} style={{ padding: '3px 6px', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '4px' }} />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '0.66rem' }}>
              <span>Max Active Trades/Symbol</span>
              <input type="number" value={config.max_active_trades_per_symbol || '1'} onChange={(e) => handleSaveConfig({ max_active_trades_per_symbol: e.target.value })} style={{ padding: '3px 6px', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '4px' }} />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '0.66rem' }}>
              <span>Avoid First 30m Breakout</span>
              <select value={config.avoid_first_30m || 'ON'} onChange={(e) => handleSaveConfig({ avoid_first_30m: e.target.value })} style={{ padding: '3px 6px', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '4px' }}>
                <option value="ON">ON</option>
                <option value="OFF">OFF</option>
              </select>
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '0.66rem' }}>
              <span>Duplicate Order Protection</span>
              <select value={config.duplicate_order_protection || 'ON'} onChange={(e) => handleSaveConfig({ duplicate_order_protection: e.target.value })} style={{ padding: '3px 6px', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '4px' }}>
                <option value="ON">ON</option>
                <option value="OFF">OFF</option>
              </select>
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '0.66rem' }}>
              <span>Telegram Alerts</span>
              <select value={config.telegram_notifications || 'OFF'} onChange={(e) => handleSaveConfig({ telegram_notifications: e.target.value })} style={{ padding: '3px 6px', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '4px' }}>
                <option value="OFF">OFF</option>
                <option value="ON">ON (Bot Notifications)</option>
              </select>
            </label>
          </div>
        </div>
      )}

      {/* Live Risk Monitor Card Grid */}
      <section className="algo-metrics-grid" style={{ margin: '0 16px 16px 16px', gridTemplateColumns: 'repeat(7, 1fr)' }}>
        <MetricTile label="Execution Status" value={sessionStatus} icon={Bot} tone={sessionStatus === 'RUNNING' ? 'good' : 'neutral'} />
        <MetricTile label="Capital Assigned" value={money(capitalAllocated)} icon={IndianRupee} />
        <MetricTile label="Available Margin" value={money(algoStatus?.portfolio?.available_funds || capitalAllocated)} icon={IndianRupee} tone="info" />
        <MetricTile label="Daily Realized/Unreal P&L" value={money(netPnL)} icon={IndianRupee} tone={netPnL >= 0 ? 'good' : 'bad'} />
        <MetricTile label="Active / Max Trades Limit" value={`${algoStatus?.portfolio?.open_positions || 0} / ${maxTradesLimit}`} icon={ListChecks} tone={algoStatus?.portfolio?.open_positions >= maxTradesLimit ? 'bad' : 'neutral'} />
        <MetricTile label="Stoploss Lock Status" value={config.daily_max_loss_lock === 'ON' ? 'PROTECTED' : 'DISABLED'} icon={ShieldCheck} tone="good" />
        <MetricTile label="Daily Max Loss Limit" value={money(maxLossLimit)} icon={IndianRupee} tone="warn" />
      </section>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', padding: '0 16px', overflow: 'visible' }}>

        {/* Dynamic Sourcing Panel */}
        <div style={{ position: 'relative', zIndex: 10 }}>
          <TerminalPanel eyebrow="Dynamic Signals Input Sourcing" title="Active Sourcing Channels" className="allow-overflow">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', overflow: 'visible' }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '20px', alignItems: 'center', overflow: 'visible' }}>
                
                {/* Autocomplete suggestions search input */}
                <div style={{ display: 'flex', gap: '6px', alignItems: 'center', overflow: 'visible' }}>
                  <span style={{ fontSize: '0.74rem', color: 'var(--muted)', fontWeight: 700 }}>Add Stock:</span>
                  <div className="watchlist-stock-search" style={{ position: 'relative', overflow: 'visible' }}>
                    <input
                      value={customSymbol}
                      onChange={(e) => {
                        setCustomSymbol(e.target.value.toUpperCase());
                        setShowStockSuggestions(true);
                      }}
                      onFocus={() => setShowStockSuggestions(true)}
                      onBlur={() => window.setTimeout(() => setShowStockSuggestions(false), 200)}
                      placeholder="RELIANCE, TCS, SBIN"
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') handleAddCustomStock();
                        if (event.key === 'Escape') setShowStockSuggestions(false);
                      }}
                      style={{
                        padding: '3px 8px',
                        fontSize: '0.76rem',
                        background: 'var(--panel-strong)',
                        border: '1px solid var(--border)',
                        color: 'var(--text)',
                        borderRadius: '4px',
                        width: '150px'
                      }}
                    />
                    {showStockSuggestions && (stockSuggestionsLoading || stockSuggestions.length > 0) && (
                      <div className="watchlist-stock-suggestions" style={{
                        position: 'absolute',
                        top: '100%',
                        left: 0,
                        zIndex: 9999,
                        background: 'var(--surface-3)',
                        border: '1px solid var(--border)',
                        borderRadius: '4px',
                        boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
                        width: '250px',
                        maxHeight: '220px',
                        overflowY: 'auto'
                      }}>
                        {stockSuggestionsLoading && <div style={{ padding: '6px', fontSize: '0.7rem', color: 'var(--muted)' }}>Searching...</div>}
                        {stockSuggestions.map((stock) => {
                          const displaySymbol = getSearchDisplaySymbol(stock);
                          return (
                            <button
                              className="watchlist-stock-suggestion"
                              key={`${stock.exchange}-${stock.symbol}`}
                              type="button"
                              onMouseDown={(event) => event.preventDefault()}
                              onClick={() => {
                                setCustomSymbol(displaySymbol);
                                setStockSuggestions([]);
                                setShowStockSuggestions(false);
                              }}
                            >
                              <span>
                                <strong>{displaySymbol}</strong>
                                <small>{stock.exchange}</small>
                              </span>
                              <em>{stock.name}</em>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                  <button
                    className="btn-primary"
                    onClick={handleAddCustomStock}
                    disabled={busy}
                    style={{ padding: '3px 8px', fontSize: '0.7rem', minHeight: '26px' }}
                  >
                    <Plus size={12} /> Add Stock
                  </button>
                </div>

                {/* Vertical divider */}
                <div style={{ width: '1px', height: '16px', background: 'var(--border)' }}></div>

                {/* Toggle Sourcing Options Button */}
                <button
                  className="btn-secondary"
                  type="button"
                  onClick={() => setShowSourcingChannels(!showSourcingChannels)}
                  style={{ padding: '3px 8px', fontSize: '0.7rem', minHeight: '26px', display: 'flex', alignItems: 'center', gap: '4px' }}
                >
                  <SlidersHorizontal size={12} />
                  {showSourcingChannels ? 'Hide Channels' : 'Source Channels'}
                </button>

                {/* Checkboxes/Toggles next to Add Stock - Visible only when toggled ON */}
                {showSourcingChannels && (
                  <>
                    <div style={{ width: '1px', height: '16px', background: 'var(--border)' }}></div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', alignItems: 'center' }}>
                      <strong style={{ color: 'var(--muted)', fontSize: '0.74rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Signals Input Channels:</strong>
                      {[
                        { key: 'source_custom', label: 'Custom Watchlist' },
                        { key: 'source_groww', label: 'Groww Source' },
                        { key: 'source_auto_scanned', label: 'Auto-Scanned' },
                        { key: 'source_high_profitable', label: 'High-Profitable' },
                        { key: 'source_prev_algo', label: 'Previous Algo' },
                        { key: 'source_premarket', label: 'Premarket' },
                      ].map((src) => {
                        const isChecked = config[src.key] !== 'OFF';
                        return (
                          <label key={src.key} style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '0.72rem', cursor: 'pointer', userSelect: 'none' }}>
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={(e) => handleSaveConfig({ [src.key]: e.target.checked ? 'ON' : 'OFF' })}
                              style={{ cursor: 'pointer' }}
                            />
                            <span style={{ fontWeight: isChecked ? 'bold' : 'normal', color: isChecked ? 'var(--text)' : 'var(--muted)' }}>{src.label}</span>
                          </label>
                        );
                      })}
                    </div>
                  </>
                )}

              </div>

              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {sources.map((src) => {
                  const mapKey = `source_${src.id === 'custom' ? 'custom' : src.id === 'groww' ? 'groww' : src.id === 'auto_scanned' ? 'auto_scanned' : src.id === 'high_profitable' ? 'high_profitable' : src.id === 'prev_algo' ? 'prev_algo' : src.id === 'premarket' ? 'premarket' : 'ALL'}`;
                  const isEnabled = src.id === 'ALL' || config[mapKey] !== 'OFF';
                  return (
                    <span key={src.id} className="preset-pill" style={{ opacity: isEnabled ? 1 : 0.35 }}>
                      <strong>{src.name}</strong>: {src.count || '-'}
                    </span>
                  );
                })}
              </div>
            </div>
          </TerminalPanel>
        </div>

        {/* 2. Top Ranked Stock Display (Card layout) */}
        {topRanked && (
          <TerminalPanel eyebrow="Top Rank Signal Highlight" title="Best Trade Opportunity Selected" className="border-highlight">
            <div className="algo-selected-trade" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '16px', background: 'var(--panel-strong)', padding: '16px', borderRadius: '6px', borderLeft: '4px solid var(--primary)' }}>
              <div><span style={{ fontSize: '0.7rem', color: 'var(--muted)' }}>Symbol</span><strong style={{ fontSize: '1.2rem', display: 'block' }}>{topRanked.symbol}</strong></div>
              <div><span style={{ fontSize: '0.7rem', color: 'var(--muted)' }}>Side</span><strong className={`status-pill ${topRanked.side === 'BUY' ? 'positive' : 'negative'}`} style={{ display: 'inline-block', marginTop: '4px' }}>{topRanked.side}</strong></div>
              <div><span style={{ fontSize: '0.7rem', color: 'var(--muted)' }}>Algo Selection Score</span><strong style={{ fontSize: '1.2rem', display: 'block', color: 'var(--primary)' }}>{number(topRanked.algo_score)}</strong></div>
              <div><span style={{ fontSize: '0.7rem', color: 'var(--muted)' }}>ML Probability</span><strong style={{ fontSize: '1.2rem', display: 'block' }}>{percent(topRanked.ml_probability)}</strong></div>
              <div><span style={{ fontSize: '0.7rem', color: 'var(--muted)' }}>Suggested Price</span><strong style={{ fontSize: '1.2rem', display: 'block' }}>{money(topRanked.entry_price)}</strong></div>
              <div><span style={{ fontSize: '0.7rem', color: 'var(--muted)' }}>Stop Loss</span><strong style={{ fontSize: '1.2rem', display: 'block', color: 'var(--negative)' }}>{money(topRanked.stop_loss)}</strong></div>
              <div><span style={{ fontSize: '0.7rem', color: 'var(--muted)' }}>Target 1</span><strong style={{ fontSize: '1.2rem', display: 'block', color: 'var(--positive)' }}>{money(topRanked.target_1)}</strong></div>
              <div><span style={{ fontSize: '0.7rem', color: 'var(--muted)' }}>Risk/Reward Ratio</span><strong style={{ fontSize: '1.2rem', display: 'block' }}>{number(topRanked.risk_reward)}x</strong></div>
              <div style={{ gridColumn: '1 / -1', borderTop: '1px solid var(--border)', paddingTop: '10px' }}>
                <span style={{ fontSize: '0.7rem', color: 'var(--muted)' }}>Strategy Justification</span>
                <p style={{ margin: '4px 0 0', fontSize: '0.8rem', color: 'var(--text-light)', lineHeight: '1.4' }}>{topRanked.ai_reason || topRanked.reason}</p>
              </div>
            </div>
          </TerminalPanel>
        )}

        {/* 3. High-Profitable Trade Suggestions */}
        <TerminalPanel eyebrow="Top Ranked Execution Pipeline" title="High-Profitable Trade Suggestions">
          {getCustomProfitableTable(highProfitable)}
        </TerminalPanel>

        {/* 4. Algo Execution Queue */}
        <TerminalPanel eyebrow="Consolidated Orders bridge" title="Algo Execution Queue" className="queue-panel">
          <DataTable
            columns={['Rank', 'Symbol', 'Side', 'Entry', 'Stop Loss', 'Target', 'Qty', 'Capital Allocation', 'Confidence', 'Algo Score', 'Execution Status', 'Sent to Algo']}
            rows={queueRows}
            emptyTitle="Execution Queue is Empty"
            emptyBody="Qualified paper orders will appear here automatically or after clicking Send to Algo."
          />
        </TerminalPanel>

        {/* 5. Algo Eligible Stocks */}
        <TerminalPanel eyebrow="Automated Sizing Matrix" title="Algo Eligible Stocks">
          {getCustomEligibleTable(eligible)}
        </TerminalPanel>

        {/* 6. Active Signals */}
        <TerminalPanel eyebrow="Realtime Signals Dashboard" title="Active Watchlist Signals">
          {getCustomSignalsTable(signals)}
        </TerminalPanel>

        {/* 7. Custom Watchlist Stocks */}
        <TerminalPanel eyebrow="Custom Watch list" title="Custom Monitored Stocks">
          <DataTable
            columns={['Symbol', 'Company', 'Source', 'Status', 'Actions']}
            rows={customStocksRows}
            emptyTitle="No Custom Stocks Added"
            emptyBody="Add stock symbols above to monitor custom picks."
          />
        </TerminalPanel>

        {/* 8. Rejected / Avoided Stocks */}
        <TerminalPanel eyebrow="Rejected Risk Audits" title="Rejected / Avoided Stocks">
          {getCustomRejectedTable(rejections)}
        </TerminalPanel>
        
      </div>
    </main>
  );
}
