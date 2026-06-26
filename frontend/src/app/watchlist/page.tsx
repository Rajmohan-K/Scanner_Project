"use client";

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Bell, BellOff, History, Pin, PinOff, Plus, RefreshCw, RotateCcw, Save, Settings2, ShieldCheck, SlidersHorizontal, Trash2 } from 'lucide-react';
import { useMarketStore } from '@/hooks/useMarketStore';
import {
  addWatchlistItem,
  searchStocks,
  localStockSearch,
  deleteWatchlistItem,
  getAlertSettings,
  getWatchlist,
  getWatchlistHistory,
  getWatchlistStreamUrl,
  saveAlertSettings,
  updateWatchlistItem,
  AlertHistoryRecord,
  WatchlistItem,
  getWatchlistAudit,
  clearWatchlistAudit,
  clearWatchlistHistory,
  type WatchlistAuditRecord,
  getGrowwIntradayStocks,
  closeSignal,
  type StockSearchResult,
} from '@/lib/api';
import {
  DEFAULT_WATCHLIST_ALERT_SETTINGS,
  desktopDeliveryLabel,
  readWatchlistAlertSettings,
  storeWatchlistAlertSettings,
  WATCHLIST_ALERT_EVENT,
} from '@/lib/watchlistAlerts';
import { PageHero, TerminalPanel, DataTable } from '@/components/terminal/TerminalPrimitives';
import { useToast } from '@/components/layout/ToastProvider';

const DEFAULT_ALERT_SETTINGS = DEFAULT_WATCHLIST_ALERT_SETTINGS;

function getSearchDisplaySymbol(stock: StockSearchResult) {
  if (stock.exchange === 'BSE') return stock.bse_symbol || stock.symbol.replace(/\.BO$/, '');
  return stock.nse_symbol || stock.symbol.replace(/\.NS$/, '');
}

function readStoredAlertSettings() {
  return readWatchlistAlertSettings();
}

function storeAlertSettingsLocal(settings: Record<string, any>) {
  storeWatchlistAlertSettings(settings);
}

function formatNumber(value: unknown, digits = 2) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : '-';
}

function formatTime(value?: string) {
  if (!value) return '-';
  return new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  }).format(new Date(value));
}

function statusTone(status?: string) {
  const value = String(status || '').toLowerCase();
  if (value.includes('ready') || value.includes('confirmed') || value.includes('breakout') || value.includes('near') || value.includes('target hit')) return 'good';
  if (value.includes('avoid') || value.includes('breakdown') || value.includes('failed') || value.includes('stop loss hit') || value.includes('stoploss hit')) return 'bad';
  return 'warn';
}

function actionTone(action?: string) {
  const value = String(action || '').toLowerCase();
  if (value.includes('buy') || value.includes('book') || value.includes('trail')) return 'good';
  if (value.includes('avoid') || value.includes('exit')) return 'bad';
  return 'warn';
}

function getActionClass(action?: string, direction?: string) {
  const act = String(action || '').toUpperCase();
  const dir = String(direction || '').toUpperCase();
  if (act === 'BUY READY') return 'buy-ready';
  if (act === 'SELL READY') return 'sell-ready';
  if (act === 'WAIT' || act.includes('WAIT')) {
    if (dir === 'SELL') return 'wait-sell';
    return 'wait-buy';
  }
  if (act === 'AVOID' || act.includes('AVOID')) return 'avoid';
  if (act.includes('BUY') || act.includes('BOOK') || act.includes('TRAIL')) return 'good';
  if (act.includes('AVOID') || act.includes('EXIT')) return 'bad';
  return 'warn';
}

function formatCurrency(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? `INR ${number.toFixed(2)}` : '-';
}

function getStockPriorityScore(item: WatchlistItem, pinnedSymbols: string[] = []): number {
  const snap = item.snapshot || {};
  const action = String(snap.action || '').toUpperCase();
  const readiness = String(snap.trade_readiness || '').toUpperCase();
  const status = String(snap.current_status || '').toUpperCase();

  let score = 0;

  // Pinned status gets the absolute highest priority boost
  if (pinnedSymbols.includes(item.symbol)) {
    score += 1000000;
  }

  // 1. Action rules
  if (action === 'BUY READY' || action === 'BUY') score += 10000;
  else if (action === 'BOOK 50%') score += 9000;
  else if (action === 'TRAIL SL') score += 8000;
  else if (action === 'EXIT') score += 7000;
  else if (action === 'WAIT') score += 5000;
  else if (action === 'ALERT ONLY') score += 4000;
  else if (action === 'WATCH') score += 3000;
  else if (action === 'AVOID') score -= 5000;

  // 2. Readiness rules
  if (readiness === 'TRADE READY' || readiness === 'BREAKOUT CONFIRMED') score += 1000;
  else if (readiness === 'NEAR BREAKOUT') score += 800;
  else if (readiness === 'VOLUME PENDING') score += 600;
  else if (readiness === 'WAITING UNTIL 11 AM') score += 500;
  else if (readiness === 'OPENING VOLATILITY - WAIT') score += 400;
  else if (readiness === 'NOT READY') score += 100;
  else if (readiness === 'AVOID') score -= 1000;

  // 3. Status rules
  if (status === 'JUST BREAKOUT') score += 500;
  else if (status === 'ABOUT TO BREAKOUT') score += 400;
  else if (status === 'NEAR BREAKOUT') score += 300;
  else if (status === 'PULLBACK') score += 200;
  else if (status === 'CONSOLIDATING') score += 100;
  else if (status === 'FAILED BREAKOUT') score -= 200;
  else if (status === 'BREAKDOWN RISK') score -= 500;
  else if (status === 'AVOID') score -= 1000;

  return score;
}

interface WatchlistRowProps {
  item: WatchlistItem;
  isSelected: boolean;
  onClick: () => void;
  checkedSymbols: string[];
  setCheckedSymbols: React.Dispatch<React.SetStateAction<string[]>>;
  pinnedSymbols: string[];
  togglePinSymbol: (symbol: string) => void;
  patchItem: (item: WatchlistItem, patch: Partial<WatchlistItem>) => void;
  removeSymbol: (item: WatchlistItem) => void;
}

const WatchlistRow = React.memo(function WatchlistRow({
  item,
  isSelected,
  onClick,
  checkedSymbols,
  setCheckedSymbols,
  pinnedSymbols,
  togglePinSymbol,
  patchItem,
  removeSymbol,
}: WatchlistRowProps) {
  // Subscribe to updates for this specific symbol only to avoid full table re-renders
  const liveTick = useMarketStore((state) => state.quotes[item.symbol]);
  
  const snap = item.snapshot || {};
  const currentPrice = liveTick ? liveTick.price : snap.current_price;
  const changePercent = liveTick ? liveTick.change_pct : snap.price_change_pct;

  // 1. Price change pulse animation
  const [pulseClass, setPulseClass] = useState('');
  const prevPriceRef = useRef<number | undefined>(currentPrice);

  useEffect(() => {
    if (currentPrice === undefined || currentPrice === null) return;
    if (prevPriceRef.current !== undefined && prevPriceRef.current !== null && prevPriceRef.current !== currentPrice) {
      if (currentPrice > prevPriceRef.current) {
        setPulseClass('pulse-up');
      } else if (currentPrice < prevPriceRef.current) {
        setPulseClass('pulse-down');
      }
      const timer = setTimeout(() => setPulseClass(''), 800);
      prevPriceRef.current = currentPrice;
      return () => clearTimeout(timer);
    } else {
      prevPriceRef.current = currentPrice;
    }
  }, [currentPrice]);

  // 2. Data Age live tracker
  const [dataAgeText, setDataAgeText] = useState('0s ago');
  const lastUpdateTime = useMemo(() => {
    const ts = liveTick?.timestamp || snap.last_checked || item.last_checked;
    return ts ? new Date(ts) : new Date();
  }, [liveTick?.timestamp, snap.last_checked, item.last_checked]);

  useEffect(() => {
    function updateAge() {
      const diffSeconds = Math.max(0, Math.floor((Date.now() - lastUpdateTime.getTime()) / 1000));
      if (diffSeconds < 60) {
        setDataAgeText(`${diffSeconds}s ago`);
      } else {
        const mins = Math.floor(diffSeconds / 60);
        const secs = diffSeconds % 60;
        setDataAgeText(`${mins}m ${secs}s ago`);
      }
    }
    updateAge();
    const ageTimer = setInterval(updateAge, 1000);
    return () => clearInterval(ageTimer);
  }, [lastUpdateTime]);

  const dir = String(snap.direction || '').toUpperCase();
  const act = String(snap.action || '').toUpperCase();
  const read = String(snap.trade_readiness || '').toUpperCase();
  const isBuy = dir === 'BUY' || act.includes('BUY') || read.includes('BUY');
  const isSell = dir === 'SELL' || act.includes('SELL') || read.includes('SELL');
  const rowBg = isBuy ? 'rgba(20, 184, 166, 0.05)' : isSell ? 'rgba(244, 63, 94, 0.05)' : undefined;

  return (
    <article 
      className={`terminal-table-row watchlist-monitor-row ${isSelected ? 'is-selected' : ''}`} 
      onClick={onClick}
      style={{ cursor: 'pointer', background: rowBg }}
    >
      <span onClick={(e) => e.stopPropagation()} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <input 
          type="checkbox"
          checked={checkedSymbols.includes(item.symbol)}
          onChange={(e) => {
            if (e.target.checked) {
              setCheckedSymbols((current) => [...current, item.symbol]);
            } else {
              setCheckedSymbols((current) => current.filter((s) => s !== item.symbol));
            }
          }}
        />
      </span>
      <strong style={{ display: 'flex', flexDirection: 'column', gap: '2px', lineHeight: '1.3' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: '4px', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden', maxWidth: '180px' }}>
          {pinnedSymbols.includes(item.symbol) && <Pin size={12} style={{ display: 'inline', color: 'var(--accent)' }} />}
          <span style={{ color: 'var(--accent)', fontSize: '0.82rem' }}>{snap.company_name || item.company_name || '-'}</span>
        </span>
        <span style={{ fontSize: '0.72rem', color: 'var(--muted)', fontWeight: 'bold' }}>
          {item.symbol}
        </span>
      </strong>
      <span className={pulseClass} style={{ transition: 'all 0.3s ease', fontWeight: pulseClass ? 'bold' : 'normal' }}>
        {formatCurrency(currentPrice)}
      </span>
      <span className={Number(changePercent) >= 0 ? 'positive' : 'negative'}>{formatNumber(changePercent)}%</span>
      <span>{formatNumber(snap.volume_spike)}x</span>
      <span>{formatNumber(snap.breakout_level)}</span>
      <span>{formatNumber(snap.resistance)}</span>
      <span>{formatNumber(snap.distance_to_breakout_pct)}%</span>
      <span className={`pill pill-${
        (() => {
          if (act.includes('AVOID') || read.includes('AVOID')) return 'warn';
          if (act.includes('BUY READY') || read.includes('BUY READY') || act === 'BUY' || read === 'BUY' || act.includes('STRONG BUY') || read.includes('STRONG BUY')) return 'good';
          if (act.includes('SELL READY') || read.includes('SELL READY') || act === 'SELL' || read === 'SELL' || act.includes('STRONG SELL') || read.includes('STRONG SELL')) return 'bad';
          return 'warn';
        })()
      }`} style={{ fontWeight: 'bold' }}>
        {(() => {
          if (act.includes('AVOID') || read.includes('AVOID')) return 'AVOID';
          if (act.includes('BUY READY') || read.includes('BUY READY') || act === 'BUY' || read === 'BUY' || act.includes('STRONG BUY') || read.includes('STRONG BUY')) return 'BUY';
          if (act.includes('SELL READY') || read.includes('SELL READY') || act === 'SELL' || read === 'SELL' || act.includes('STRONG SELL') || read.includes('STRONG SELL')) return 'SELL';
          return 'WATCH';
        })()}
      </span>
      <span>{snap.suggested_time || '-'}</span>
      <span>{item.last_alert || snap.last_alert || '-'}</span>
    </article>
  );
});

function StockChart({ candles, currentPrice }: { candles?: any[]; currentPrice?: number }) {
  const points = useMemo(() => {
    if (!Array.isArray(candles) || candles.length === 0) return [];
    // Extract close prices
    const prices = candles.map(c => Number(c.close || c.price || 0)).filter(p => p > 0);
    if (prices.length === 0 && currentPrice) {
      return [currentPrice];
    }
    return prices;
  }, [candles, currentPrice]);

  if (points.length < 2) {
    return (
      <div style={{ height: '140px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: '0.74rem', background: 'rgba(0,0,0,0.1)', border: '1px solid rgba(255,255,255,0.03)', borderRadius: '6px' }}>
        Awaiting more price trend ticks...
      </div>
    );
  }

  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min === 0 ? 1 : max - min;
  
  const padding = 10;
  const height = 140;
  const width = 300;
  
  const stepX = (width - padding * 2) / (points.length - 1);
  const scaleY = (height - padding * 2) / range;
  
  const svgPoints = points.map((p, i) => {
    const x = padding + i * stepX;
    const y = height - padding - (p - min) * scaleY;
    return `${x},${y}`;
  }).join(' ');

  const strokeColor = points[points.length - 1] >= points[0] ? '#5eead4' : '#fb7185';
  
  const areaPoints = `${padding},${height - padding} ${svgPoints} ${width - padding},${height - padding}`;

  return (
    <div style={{ padding: '8px', background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.04)', borderRadius: '6px', width: '100%', boxSizing: 'border-box' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
        <span style={{ fontSize: '0.64rem', fontWeight: 800, color: 'var(--accent)', textTransform: 'uppercase' }}>Price Trend (Last 10 Ticks)</span>
        <span style={{ fontSize: '0.68rem', color: strokeColor === '#5eead4' ? '#34d399' : '#fb7185', fontWeight: 'bold' }}>
          {points[points.length - 1] >= points[0] ? '▲ BULLISH' : '▼ BEARISH'}
        </span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height}>
        <defs>
          <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={strokeColor} stopOpacity="0.25" />
            <stop offset="100%" stopColor={strokeColor} stopOpacity="0.0" />
          </linearGradient>
        </defs>
        
        <line x1={padding} y1={padding} x2={width - padding} y2={padding} stroke="rgba(255,255,255,0.03)" strokeWidth="1" />
        <line x1={padding} y1={height / 2} x2={width - padding} y2={height / 2} stroke="rgba(255,255,255,0.03)" strokeWidth="1" />
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="rgba(255,255,255,0.03)" strokeWidth="1" />

        <polygon points={areaPoints} fill="url(#chartGradient)" />
        
        <polyline
          fill="none"
          stroke={strokeColor}
          strokeWidth="2.5"
          points={svgPoints}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        <circle cx={padding} cy={height - padding - (points[0] - min) * scaleY} r="3" fill={strokeColor} />
        <circle cx={width - padding} cy={height - padding - (points[points.length - 1] - min) * scaleY} r="4" fill={strokeColor} stroke="#ffffff" strokeWidth="1.5" />
      </svg>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.62rem', color: 'var(--muted)', marginTop: '4px' }}>
        <span>Min: INR {min.toFixed(2)}</span>
        <span>Max: INR {max.toFixed(2)}</span>
      </div>
    </div>
  );
}

function StockDetailsPanel({ 
  item, 
  snap, 
  currentPrice, 
  pinnedSymbols, 
  togglePinSymbol, 
  patchItem, 
  removeSymbol, 
  onClose,
  minWidth = '950px' 
}: { 
  item: WatchlistItem; 
  snap: any; 
  currentPrice?: number; 
  pinnedSymbols: string[]; 
  togglePinSymbol: (sym: string) => void; 
  patchItem: (item: WatchlistItem, patch: any) => void; 
  removeSymbol: (item: WatchlistItem) => void; 
  onClose: () => void;
  minWidth?: string;
}) {
  return (
    <div 
      className="custom-stock-detail-inline" 
      onClick={(e) => e.stopPropagation()}
      style={{ 
        gridColumn: '1 / -1', 
        background: 'rgba(10, 20, 35, 0.96)', 
        borderTop: '1px solid var(--accent)', 
        borderBottom: '1px solid var(--accent)', 
        padding: '10px 14px',
        color: 'var(--text)',
        width: '100%',
        minWidth: minWidth,
        boxSizing: 'border-box'
      }}
    >
      <div style={{
        position: 'sticky',
        left: '20px',
        maxWidth: '1200px',
        width: '100%',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '6px' }}>
          <h3 style={{ margin: 0, fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <strong style={{ color: 'var(--accent)' }}>{item.symbol}</strong>
            <span style={{ fontSize: '0.78rem', color: 'var(--muted)' }}>{snap.company_name || item.company_name || '-'}</span>
          </h3>
          <div style={{ display: 'flex', gap: '6px' }}>
            <button 
              className="btn-secondary" 
              type="button" 
              onClick={() => togglePinSymbol(item.symbol)}
              style={{ display: 'flex', alignItems: 'center', gap: '4px', padding: '2px 6px', fontSize: '0.72rem', minHeight: '22px' }}
            >
              {pinnedSymbols.includes(item.symbol) ? (
                <>
                  <PinOff size={11} /> Unpin
                </>
              ) : (
                <>
                  <Pin size={11} /> Pin
                </>
              )}
            </button>
            <button 
              className="btn-secondary" 
              type="button" 
              onClick={() => patchItem(item, { monitoring_enabled: item.monitoring_enabled === false })}
              style={{ display: 'flex', alignItems: 'center', gap: '4px', padding: '2px 6px', fontSize: '0.72rem', minHeight: '22px' }}
            >
              {item.monitoring_enabled === false ? (
                <>
                  <BellOff size={11} /> Enable Monitoring
                </>
              ) : (
                <>
                  <Bell size={11} /> Disable Monitoring
                </>
              )}
            </button>
            <button 
              className="btn-secondary" 
              type="button" 
              onClick={() => {
                if (confirm(`Remove ${item.symbol} from watchlist?`)) {
                  removeSymbol(item);
                  onClose();
                }
              }}
              style={{ display: 'flex', alignItems: 'center', gap: '4px', padding: '2px 6px', fontSize: '0.72rem', minHeight: '22px', background: 'rgba(255, 100, 100, 0.1)', color: '#ff6b6b', border: '1px solid rgba(255, 100, 100, 0.2)' }}
            >
              <Trash2 size={11} /> Remove
            </button>
            <button 
              className="btn-secondary" 
              type="button" 
              onClick={onClose}
              style={{ padding: '2px 6px', fontSize: '0.72rem', minHeight: '22px', background: 'rgba(255, 255, 255, 0.05)', color: 'var(--text)', border: '1px solid var(--border)' }}
            >
              Close
            </button>
          </div>
        </div>

        {/* Dedicated Metadata & Exchange Availability Row */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '16px',
          flexWrap: 'wrap',
          background: 'rgba(255,255,255,0.03)',
          border: '1px solid rgba(255,255,255,0.05)',
          borderRadius: '6px',
          padding: '8px 12px',
          fontSize: '0.74rem',
          color: 'var(--text-bright)'
        }}>
          <div>
            <span style={{ color: 'var(--muted)', marginRight: '6px' }}>ISIN:</span>
            <strong>{snap.isin || item.isin || '-'}</strong>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ color: 'var(--muted)' }}>Exchange Availability:</span>
            <span style={{ display: 'flex', gap: '8px' }}>
              <span style={{ padding: '2px 6px', background: 'rgba(255,255,255,0.06)', borderRadius: '3px', fontSize: '0.68rem' }}>
                NSE: <strong>{snap.nse_symbol || item.nse_symbol || '-'}</strong>
              </span>
              <span style={{ padding: '2px 6px', background: 'rgba(255,255,255,0.06)', borderRadius: '3px', fontSize: '0.68rem' }}>
                BSE: <strong>{snap.bse_symbol || item.bse_symbol || '-'}</strong>
              </span>
            </span>
          </div>
          <div>
            <span style={{ color: 'var(--muted)', marginRight: '6px' }}>Preferred Exchange:</span>
            <strong style={{ color: 'var(--accent)' }}>{snap.exchange || item.exchange || 'NSE'}</strong>
          </div>
          <div>
            <span style={{ color: 'var(--muted)', marginRight: '6px' }}>Selected Source:</span>
            <strong className={`pill pill-${snap.active_quote_source === 'BSE' ? 'warn' : 'good'}`} style={{ fontSize: '0.68rem', padding: '2px 6px', borderRadius: '3px' }}>
              {snap.active_quote_source || item.active_quote_source || 'NSE'}
            </strong>
            {snap.fallback_reason && (
              <span style={{ color: 'var(--warning)', marginLeft: '6px', fontSize: '0.68rem' }}>
                ({snap.fallback_reason})
              </span>
            )}
          </div>
          <div>
            <span style={{ color: 'var(--muted)', marginRight: '6px' }}>Sector:</span>
            <strong style={{ color: 'var(--accent)' }}>{snap.sector || item.snapshot?.sector || '-'}</strong>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1.1fr 0.9fr 1.2fr', gap: '12px' }}>
          {/* Column 1: TRADE DECISION */}
          <div style={{ background: 'rgba(255,255,255,0.02)', padding: '8px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.04)' }}>
            <span style={{ fontSize: '0.66rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--accent)', display: 'block', marginBottom: '6px' }}>TRADE DECISION</span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', fontSize: '0.72rem' }}>
              <div>
                <span style={{ color: 'var(--muted)' }}>Direction:</span>{' '}
                <strong style={{ color: snap.direction === 'SELL' ? '#fb7185' : '#34d399' }}>{snap.direction || 'BUY'}</strong>
              </div>
              <div>
                <span style={{ color: 'var(--muted)' }}>Decision:</span>{' '}
                <span className={`pill pill-${getActionClass(snap.trade_readiness, snap.direction)}`} style={{ fontWeight: 800 }}>{snap.trade_readiness || 'AVOID'}</span>
              </div>
              <div>
                <span style={{ color: 'var(--muted)' }}>Suggested At:</span>{' '}
                <strong>{snap.suggested_at || '-'}</strong>
              </div>
              <div>
                <span style={{ color: 'var(--muted)' }}>Quality Score:</span>{' '}
                <strong style={{ color: 'var(--accent)' }}>{snap.quality_score || 0} / 100</strong>{' '}
                <span className={`pill pill-${statusTone(snap.quality_label)}`} style={{ fontSize: '0.62rem', padding: '1px 4px' }}>{snap.quality_label || 'Avoid'}</span>
              </div>
              <div style={{ marginTop: '3px', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '3px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '3px' }}>
                <div><span style={{ color: 'var(--muted)', fontSize: '0.62rem' }}>Entry:</span> <strong>{formatCurrency(snap.entry)}</strong></div>
                <div><span style={{ color: 'var(--muted)', fontSize: '0.62rem' }}>Stop Loss:</span> <strong style={{ color: 'var(--negative)' }}>{formatCurrency(snap.stop_loss)}</strong></div>
                <div><span style={{ color: 'var(--muted)', fontSize: '0.62rem' }}>Target 1:</span> <strong>{formatCurrency(snap.target1)}</strong></div>
                <div><span style={{ color: 'var(--muted)', fontSize: '0.62rem' }}>Target 2:</span> <strong>{formatCurrency(snap.target2)}</strong></div>
              </div>
              <div style={{ marginTop: '3px', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '3px', display: 'grid', gridTemplateColumns: '1.2fr 1fr 0.8fr', gap: '3px' }}>
                <div><span style={{ color: 'var(--muted)', fontSize: '0.62rem' }}>Expected Profit:</span> <strong className="positive">{formatNumber(snap.expected_profit_percent)}%</strong></div>
                <div><span style={{ color: 'var(--muted)', fontSize: '0.62rem' }}>Risk:</span> <strong className="negative">{formatNumber(snap.expected_loss_percent)}%</strong></div>
                <div><span style={{ color: 'var(--muted)', fontSize: '0.62rem' }}>R:R:</span> <strong>{formatNumber(snap.risk_reward_ratio)}</strong></div>
              </div>
            </div>
          </div>

          {/* Column 2: SINCE SUGGESTION */}
          <div style={{ background: 'rgba(255,255,255,0.02)', padding: '8px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.04)' }}>
            <span style={{ fontSize: '0.66rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--accent)', display: 'block', marginBottom: '6px' }}>SINCE SUGGESTION</span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', fontSize: '0.72rem' }}>
              <div>
                <span style={{ color: 'var(--muted)' }}>Current P/L:</span>{' '}
                <strong className={Number(snap.current_gain_loss_percent) >= 0 ? 'positive' : 'negative'} style={{ fontSize: '0.8rem' }}>
                  {Number(snap.current_gain_loss_percent) >= 0 ? `+${formatNumber(snap.current_gain_loss_percent)}%` : `${formatNumber(snap.current_gain_loss_percent)}%`}
                </strong>
              </div>
              <div>
                <span style={{ color: 'var(--muted)' }}>Max Gain:</span>{' '}
                <strong className="positive">+{formatNumber(snap.max_gain_after_suggestion)}%</strong>
              </div>
              <div>
                <span style={{ color: 'var(--muted)' }}>Max Loss (Drawdown):</span>{' '}
                <strong className="negative">{formatNumber(snap.max_loss_after_suggestion)}%</strong>
              </div>
              <div>
                <span style={{ color: 'var(--muted)' }}>Time Active:</span>{' '}
                <strong>{snap.time_since_suggestion || '0s'}</strong>
              </div>
              <div>
                <span style={{ color: 'var(--muted)' }}>Status:</span>{' '}
                <span className={`pill pill-${statusTone(snap.suggestion_status)}`} style={{ fontWeight: 700 }}>
                  {snap.suggestion_status || 'Waiting'}
                </span>
              </div>
              
              {/* Trailing Stop Details */}
              <div style={{ marginTop: '4px', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '4px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <span style={{ fontSize: '0.62rem', fontWeight: 700, color: 'var(--accent)', display: 'block' }}>TRAILING STOP SYSTEM</span>
                <div>
                  <span style={{ color: 'var(--muted)' }}>Initial Stop Loss:</span>{' '}
                  <strong>{snap.initialStopLoss ? formatCurrency(snap.initialStopLoss) : '-'}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--muted)' }}>Trailing Stop:</span>{' '}
                  <strong style={{ color: 'var(--warning)' }}>{snap.trailingStop ? formatCurrency(snap.trailingStop) : '-'}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--muted)' }}>Trailing Active:</span>{' '}
                  <strong style={{ color: snap.trailingActivated ? 'var(--good)' : 'var(--muted)' }}>
                    {snap.trailingActivated ? 'Yes' : 'No'}
                  </strong>
                </div>
                <div>
                  <span style={{ color: 'var(--muted)' }}>Highest Since Entry:</span>{' '}
                  <strong className="positive">{snap.highestPriceSinceEntry ? formatCurrency(snap.highestPriceSinceEntry) : '-'}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--muted)' }}>Lowest Since Entry:</span>{' '}
                  <strong className="negative">{snap.lowestPriceSinceEntry ? formatCurrency(snap.lowestPriceSinceEntry) : '-'}</strong>
                </div>
                {snap.outcome && (
                  <div>
                    <span style={{ color: 'var(--muted)' }}>Exit Reason:</span>{' '}
                    <span className="pill pill-warn" style={{ fontSize: '0.68rem', fontWeight: 'bold' }}>{snap.outcome}</span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Column 3: ANALYSIS */}
          <div style={{ background: 'rgba(255,255,255,0.02)', padding: '8px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.04)' }}>
            <span style={{ fontSize: '0.66rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--accent)', display: 'block', marginBottom: '6px' }}>ANALYSIS</span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.72rem' }}>
              <div>
                <span style={{ color: 'var(--muted)', display: 'block', marginBottom: '3px', fontWeight: 600 }}>Reason:</span>
                <div style={{ 
                  background: 'rgba(0, 0, 0, 0.25)', 
                  padding: '4px 6px', 
                  borderRadius: '4px', 
                  border: '1px solid rgba(255,255,255,0.03)',
                  fontSize: '0.68rem',
                  color: 'var(--text-bright)',
                  fontWeight: 500,
                  lineHeight: '1.25'
                }}>
                  {snap.reason || 'No active analysis available. Waiting for backend cycle.'}
                </div>
              </div>
              <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '4px' }}>
                <span style={{ color: 'var(--muted)', display: 'block', marginBottom: '3px', fontWeight: 600, fontSize: '0.64rem' }}>SETUP CHECKLIST:</span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                  {(() => {
                    const isSell = snap.direction === 'SELL';
                    const checklist = isSell ? [
                      { label: 'Min Downside (>= 1.5%)', val: `${formatNumber(snap.expected_profit_percent)}%`, passed: (snap.expected_profit_percent ?? 0) >= 1.5 },
                      { label: 'R:R Ratio (>= 1.8)', val: formatNumber(snap.risk_reward_ratio), passed: (snap.risk_reward_ratio ?? 0) >= 1.8 },
                      { label: 'Relative Vol (>= 2.0x)', val: `${formatNumber(snap.volume_spike)}x`, passed: (snap.volume_spike ?? 0) >= 2.0 },
                      { label: 'Price vs VWAP (< VWAP)', val: (snap.current_price ?? 0) < (snap.vwap ?? 0) ? 'Below' : 'Above', passed: (snap.current_price ?? 0) < (snap.vwap ?? 0) },
                      { label: 'Dist to BD (<= 0.3%)', val: `${formatNumber(snap.distance_to_breakout_pct)}%`, passed: (snap.current_price ?? 0) <= (snap.breakout_level ?? 0) || (snap.distance_to_breakout_pct ?? 0) <= 0.3 },
                      { label: 'Intraday Drop (>= -3.5%)', val: `${formatNumber(snap.price_change_pct)}%`, passed: (snap.price_change_pct ?? 0) >= -3.5 },
                      { label: 'Dist from Low (>= 0.4%)', val: `${formatNumber(snap.distance_from_intraday_high_percent)}%`, passed: (snap.distance_from_intraday_high_percent ?? 0) >= 0.4 },
                      { label: 'Quality Score (>= 75)', val: `${snap.quality_score ?? 0}`, passed: (snap.quality_score ?? 0) >= 75 }
                    ] : [
                      { label: 'Min Profit (>= 1.5%)', val: `${formatNumber(snap.expected_profit_percent)}%`, passed: (snap.expected_profit_percent ?? 0) >= 1.5 },
                      { label: 'R:R Ratio (>= 1.8)', val: formatNumber(snap.risk_reward_ratio), passed: (snap.risk_reward_ratio ?? 0) >= 1.8 },
                      { label: 'Relative Vol (>= 2.0x)', val: `${formatNumber(snap.volume_spike)}x`, passed: (snap.volume_spike ?? 0) >= 2.0 },
                      { label: 'Price vs VWAP (>= VWAP)', val: (snap.current_price ?? 0) >= (snap.vwap ?? 0) ? 'Above' : 'Below', passed: (snap.current_price ?? 0) >= (snap.vwap ?? 0) },
                      { label: 'Dist to BO (<= 0.3%)', val: `${formatNumber(snap.distance_to_breakout_pct)}%`, passed: (snap.current_price ?? 0) >= (snap.breakout_level ?? 0) || (snap.distance_to_breakout_pct ?? 0) <= 0.3 },
                      { label: 'Intraday Run-up (<= 3.5%)', val: `${formatNumber(snap.price_change_pct)}%`, passed: (snap.price_change_pct ?? 0) <= 3.5 },
                      { label: 'Dist from High (>= 0.4%)', val: `${formatNumber(snap.distance_from_intraday_high_percent)}%`, passed: (snap.distance_from_intraday_high_percent ?? 0) >= 0.4 },
                      { label: 'Quality Score (>= 75)', val: `${snap.quality_score ?? 0}`, passed: (snap.quality_score ?? 0) >= 75 }
                    ];
                    return checklist.map((rule, idx) => (
                      <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.62rem' }}>
                        <span style={{ color: rule.passed ? 'var(--text)' : 'var(--muted)', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden', maxWidth: '120px' }}>
                          {rule.passed ? '✓' : '✗'} {rule.label}
                        </span>
                        <strong style={{ color: rule.passed ? 'var(--accent)' : 'var(--negative)' }}>{rule.val}</strong>
                      </div>
                    ));
                  })()}
                </div>
              </div>
            </div>
          </div>

          {/* Column 4: ALERT CONFIGURATION */}
          <div style={{ background: 'rgba(255,255,255,0.02)', padding: '8px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.04)' }}>
            <span style={{ fontSize: '0.66rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--accent)', display: 'block', marginBottom: '6px' }}>ALERT CONFIGURATION</span>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '3px 4px' }}>
              {[
                ['custom_breakout_price', 'Custom Breakout'],
                ['custom_support', 'Custom Support'],
                ['custom_price_alert', 'Price Alert'],
                ['telegram_enabled', 'Telegram Alert', 'checkbox'],
                ['volume_alerts_enabled', 'Volume Alert', 'checkbox'],
                ['target_alerts_enabled', 'Target Alert', 'checkbox'],
                ['stop_loss_alerts_enabled', 'SL Alert', 'checkbox'],
              ].map(([key, label, type]) => {
                if (type === 'checkbox') {
                  return (
                    <label key={key} style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.68rem', cursor: 'pointer', background: 'rgba(255,255,255,0.02)', padding: '4px 6px', borderRadius: '4px', border: '1px solid rgba(255,255,255,0.03)' }}>
                      <input 
                        type="checkbox" 
                        checked={Boolean((item as any)[key] ?? snap[key])} 
                        onChange={(e) => patchItem(item, { [key]: e.target.checked })}
                      />
                      <span>{label}</span>
                    </label>
                  );
                }
                return (
                  <label key={key} style={{ display: 'flex', flexDirection: 'column', gap: '1px', fontSize: '0.65rem' }}>
                    <span style={{ color: 'var(--muted)', fontWeight: 600 }}>{label}</span>
                    <input 
                      type="number" 
                      defaultValue={(item as any)[key] ?? snap[key] ?? ''} 
                      onBlur={(e) => patchItem(item, { [key]: Number(e.target.value) || undefined })}
                      style={{ padding: '2px 4px', fontSize: '0.7rem', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '3px', width: '100%', boxSizing: 'border-box' }}
                    />
                  </label>
                );
              })}
            </div>
          </div>

          {/* Column 5: REAL-TIME Price Trend Chart */}
          <div style={{ background: 'rgba(255,255,255,0.02)', padding: '8px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.04)', display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '0.66rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--accent)', display: 'block', marginBottom: '6px' }}>REAL-TIME Price CHART</span>
            <StockChart candles={snap.candles} currentPrice={currentPrice} />
          </div>
        </div>
      </div>
    </div>
  );
}

let globalWatchlistCache: WatchlistItem[] = [];
let globalHistoryCache: AlertHistoryRecord[] = [];
let globalAuditCache: WatchlistAuditRecord[] = [];
let globalSettingsCache: Record<string, any> = {};

export default function WatchlistPage() {
  const toast = useToast();
  const quotes = useMarketStore((state) => state.quotes);
  const [items, setItems] = useState<WatchlistItem[]>(() => globalWatchlistCache);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [symbol, setSymbol] = useState('');
  const [stockSuggestions, setStockSuggestions] = useState<StockSearchResult[]>([]);
  const [stockSuggestionsLoading, setStockSuggestionsLoading] = useState(false);
  const [showStockSuggestions, setShowStockSuggestions] = useState(false);
  const [selected, setSelected] = useState<WatchlistItem | null>(null);
  const [selectedActiveSignal, setSelectedActiveSignal] = useState<string | null>(null);
  const [settings, setSettings] = useState<Record<string, any>>(() => Object.keys(globalSettingsCache).length ? globalSettingsCache : DEFAULT_ALERT_SETTINGS);
  const [history, setHistory] = useState<AlertHistoryRecord[]>(() => globalHistoryCache);
  const [auditHistory, setAuditHistory] = useState<WatchlistAuditRecord[]>(() => globalAuditCache);
  const [historyFilters, setHistoryFilters] = useState<Record<string, string>>({});
  const [connection, setConnection] = useState('Connecting');
  const [settingsDirty, setSettingsDirty] = useState(false);
  const settingsLoaded = useRef(false);
  const [loadingAudit, setLoadingAudit] = useState(false);
  const [auditError, setAuditError] = useState('');

  const [filterQuery, setFilterQuery] = useState('');
  const [filterReadiness, setFilterReadiness] = useState('');
  const [filterAction, setFilterAction] = useState('');
  const [filterAlerts, setFilterAlerts] = useState('');
  const [filterSource, setFilterSource] = useState('all');
  const [filterDirection, setFilterDirection] = useState('all');
  const [showSettings, setShowSettings] = useState(false);
  const [checkedSymbols, setCheckedSymbols] = useState<string[]>([]);
  const [displayLimit, setDisplayLimit] = useState<number | 'all'>(10);
  const [showLiveFilters, setShowLiveFilters] = useState(true);
  const [liveMonitorMode, setLiveMonitorMode] = useState(true);
  const loadInFlightRef = useRef(false);
  const lastStreamUpdateRef = useRef(Date.now());

  const activeSuggestions = useMemo(() => {
    return items.filter((item) => {
      const snap = item.snapshot || {};
      const status = String(snap.suggestion_status || '').toUpperCase();
      return status && !['CLOSED', 'STOP LOSS HIT', 'TARGET HIT'].includes(status);
    });
  }, [items]);

  const [pinnedSymbols, setPinnedSymbols] = useState<string[]>(() => {
    if (typeof window !== 'undefined') {
      try {
        const stored = window.localStorage.getItem('scanner-watchlist-pinned-symbols');
        return stored ? JSON.parse(stored) : [];
      } catch {
        return [];
      }
    }
    return [];
  });

  const togglePinSymbol = (symbol: string) => {
    setPinnedSymbols((current) => {
      const isPinned = current.includes(symbol);
      const next = isPinned ? current.filter((s) => s !== symbol) : [...current, symbol];
      if (typeof window !== 'undefined') {
        window.localStorage.setItem('scanner-watchlist-pinned-symbols', JSON.stringify(next));
      }
      toast.push(isPinned ? `${symbol} unpinned` : `${symbol} pinned to top`, 'success');
      return next;
    });
  };

  const filteredItems = useMemo(() => {
    const seenSymbols = new Set<string>();
    const list = items.filter((item) => {
      const symbolKey = String(item.symbol).toUpperCase();
      if (seenSymbols.has(symbolKey)) return false;
      seenSymbols.add(symbolKey);

      const snap = item.snapshot || {};
      
      if (filterQuery) {
        const query = filterQuery.toLowerCase();
        const matchesSym = item.symbol.toLowerCase().includes(query);
        const matchesCompany = (snap.company_name || item.company_name || '').toLowerCase().includes(query);
        if (!matchesSym && !matchesCompany) return false;
      }
      
      if (filterReadiness) {
        const readiness = String(snap.trade_readiness || '').toLowerCase();
        if (!readiness.includes(filterReadiness.toLowerCase())) return false;
      }
      
      if (filterAction) {
        const action = String(snap.action || '').toLowerCase();
        if (!action.includes(filterAction.toLowerCase())) return false;
      }
      
      if (filterAlerts) {
        const isEnabled = item.alerts_enabled !== false;
        if (filterAlerts === 'on' && !isEnabled) return false;
        if (filterAlerts === 'off' && isEnabled) return false;
      }

      if (filterSource !== 'all') {
        const itemSource = String(item.source || 'CUSTOM').toLowerCase();
        if (filterSource === 'groww' && itemSource !== 'groww') return false;
        if (filterSource === 'custom' && itemSource !== 'custom') return false;
      }
      
      if (filterDirection !== 'all') {
        const snapDir = String(snap.direction || 'BUY').toUpperCase();
        const action = String(snap.action || '').toUpperCase();
        const readiness = String(snap.trade_readiness || '').toUpperCase();
        const isHighAlert = snap.is_high_alert || ((snap.quality_score ?? 0) >= 80 && (snap.expected_profit_percent ?? 0) >= 1.5 && (snap.risk_reward_ratio ?? 0) >= 1.8 && (snap.volume_spike ?? 0) >= 2.0);

        if (filterDirection === 'buy_opp' && snapDir !== 'BUY') return false;
        if (filterDirection === 'sell_opp' && snapDir !== 'SELL') return false;
        if (filterDirection === 'buy_ready' && action !== 'BUY READY' && readiness !== 'BUY READY') return false;
        if (filterDirection === 'sell_ready' && action !== 'SELL READY' && readiness !== 'SELL READY') return false;
        if (filterDirection === 'wait' && !action.includes('WAIT') && !readiness.includes('WAIT')) return false;
        if (filterDirection === 'avoid' && !action.includes('AVOID') && !readiness.includes('AVOID')) return false;
        if (filterDirection === 'high_alert' && !isHighAlert) return false;
      }
      
      return true;
    });

    return list.sort((a, b) => {
      // 1. Pinned status gets absolute priority
      const pinA = pinnedSymbols.includes(a.symbol) ? 1 : 0;
      const pinB = pinnedSymbols.includes(b.symbol) ? 1 : 0;
      if (pinA !== pinB) {
        return pinB - pinA;
      }

      // Fall back to original priority score
      const scoreA = getStockPriorityScore(a, pinnedSymbols);
      const scoreB = getStockPriorityScore(b, pinnedSymbols);
      if (scoreA !== scoreB) {
        return scoreB - scoreA;
      }
      
      const distA = a.snapshot?.distance_to_breakout_pct ?? 999;
      const distB = b.snapshot?.distance_to_breakout_pct ?? 999;
      if (distA !== distB) {
        return distA - distB;
      }

      return a.symbol.localeCompare(b.symbol);
    });
  }, [items, filterQuery, filterReadiness, filterAction, filterAlerts, filterSource, pinnedSymbols, filterDirection]);

  async function load(options: { background?: boolean } = {}) {
    if (loadInFlightRef.current) return;
    loadInFlightRef.current = true;
    const background = Boolean(options.background);
    if (!background) {
      setLoading(true);
      setLoadingAudit(true);
      setError('');
      setAuditError('');
    }
    try {
      const [watchlist, alertSettings, auditResponse] = await Promise.all([
        getWatchlist(),
        background ? Promise.resolve({ settings: globalSettingsCache }) : getAlertSettings(),
        background ? Promise.resolve({ audit: globalAuditCache }) : getWatchlistAudit().catch(err => {
          setAuditError(err?.message || 'Failed to load watchlist outcomes');
          return { audit: globalAuditCache };
        })
      ]);
      const storedSettings = readStoredAlertSettings();
      const mergedSettings = {
        ...DEFAULT_ALERT_SETTINGS,
        ...(alertSettings.settings || {}),
        ...storedSettings,
      };
      globalWatchlistCache = watchlist.items || [];
      globalSettingsCache = mergedSettings;
      
      setItems(globalWatchlistCache);
      setSettings(mergedSettings);
      storeAlertSettingsLocal(mergedSettings);
      
      if (!background) {
        const historyResponse = await getWatchlistHistory({ limit: 80 });
        globalHistoryCache = historyResponse.alerts || [];
        setHistory(globalHistoryCache);
      }
      
      globalAuditCache = auditResponse.audit || [];
      setAuditHistory(globalAuditCache);
    } catch (err: any) {
      if (!background || globalWatchlistCache.length === 0) {
        const storedSettings = readStoredAlertSettings();
        const nextSettings = {
          ...DEFAULT_ALERT_SETTINGS,
          ...storedSettings,
        };
        setSettings(nextSettings);
        setError(`${err?.message || 'Unable to load watchlist'} - backend may need restart on port 5000`);
      }
    } finally {
      settingsLoaded.current = true;
      loadInFlightRef.current = false;
      if (!background) {
        setLoading(false);
        setLoadingAudit(false);
      }
    }
  }

  useEffect(() => {
    const storedSettings = readStoredAlertSettings();
    if (Object.keys(storedSettings).length) {
      setSettings({ ...DEFAULT_ALERT_SETTINGS, ...storedSettings });
    }
    load();
  }, []);

  useEffect(() => {
    if (!settingsLoaded.current || !settingsDirty) return;
    const timer = window.setTimeout(async () => {
      try {
        const response = await saveAlertSettings(settings);
        const savedSettings = { ...DEFAULT_ALERT_SETTINGS, ...(response.settings || settings) };
        setSettings(savedSettings);
        storeAlertSettingsLocal(savedSettings);
        setSettingsDirty(false);
      } catch {
        // Keep the local draft. The explicit Save button reports backend errors.
      }
    }, 700);
    return () => window.clearTimeout(timer);
  }, [settings, settingsDirty]);

  useEffect(() => {
    const source = new EventSource(getWatchlistStreamUrl());
    source.onopen = () => setConnection('Live');
    source.onerror = () => setConnection('Reconnecting');
    source.addEventListener('WATCHLIST_UPDATED', (event) => {
      try {
        const payload = JSON.parse((event as MessageEvent).data);
        lastStreamUpdateRef.current = Date.now();
        globalWatchlistCache = payload.items || [];
        setItems(globalWatchlistCache);
        setLoading(false);
        const alerts = payload.alerts || [];
        if (Array.isArray(alerts)) {
          globalHistoryCache = alerts;
          setHistory(alerts);
        }
        if (payload.audit && Array.isArray(payload.audit)) {
          globalAuditCache = payload.audit;
          setAuditHistory(payload.audit);
        }
      } catch {
        setConnection('Stream error');
      }
    });

    // Recovery only: the stream is the live path, so avoid overlapping full reloads.
    const fallbackInterval = setInterval(() => {
      if (Date.now() - lastStreamUpdateRef.current > 5000) {
        load({ background: true });
      }
    }, 5000);

    return () => {
      source.close();
      clearInterval(fallbackInterval);
    };
  }, []);



  useEffect(() => {
    function handleAlert(event: Event) {
      const alert = (event as CustomEvent<AlertHistoryRecord>).detail;
      if (!alert?.alert_id) return;
      globalHistoryCache = [alert, ...globalHistoryCache.filter((row) => row.alert_id !== alert.alert_id)].slice(0, 100);
      setHistory(globalHistoryCache);
    }
    window.addEventListener(WATCHLIST_ALERT_EVENT, handleAlert);
    return () => window.removeEventListener(WATCHLIST_ALERT_EVENT, handleAlert);
  }, []);

  useEffect(() => {
    const activeToken = symbol.split(',').pop()?.trim() || '';
    if (!showStockSuggestions || activeToken.length < 2) {
      setStockSuggestions([]);
      setStockSuggestionsLoading(false);
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
  }, [symbol, showStockSuggestions]);

  const stats = useMemo(() => {
    const monitored = items.filter((item) => item.monitoring_enabled !== false).length;
    const alerts = items.filter((item) => item.alerts_enabled !== false).length;
    const tradeReady = items.filter((item) => String(item.snapshot?.trade_readiness || '').toLowerCase().includes('ready')).length;
    const wait = items.filter((item) => String(item.snapshot?.action || '').toLowerCase() === 'wait').length;
    return { monitored, alerts, tradeReady, wait };
  }, [items]);

  function selectStockSuggestion(stock: StockSearchResult) {
    const parts = symbol.split(',');
    parts[parts.length - 1] = ` ${getSearchDisplaySymbol(stock)}`;
    setSymbol(parts.join(',').trimStart());
    setStockSuggestions([]);
    setShowStockSuggestions(false);
  }

  async function addSymbol(nextSymbol?: string) {
    const raw = (nextSymbol || symbol).trim();
    if (!raw) return;
    try {
      const response = await addWatchlistItem({ symbol: raw, monitoring_enabled: true, alerts_enabled: true, telegram_enabled: true });
      setSymbol('');
      setStockSuggestions([]);
      setShowStockSuggestions(false);
      if (response.items && Array.isArray(response.items)) {
        globalWatchlistCache = response.items;
        setItems(globalWatchlistCache);
        const addedNames = response.items.map((item) => item.symbol).join(', ');
        toast.push(`${addedNames} added to watchlist monitor`, 'success');
      } else {
        globalWatchlistCache = [response.item, ...globalWatchlistCache.filter((item) => item.symbol !== response.item.symbol)];
        setItems(globalWatchlistCache);
        toast.push(`${response.item.symbol} added to watchlist monitor`, 'success');
      }
    } catch (err: any) {
      toast.push(err.response?.data?.message || err?.message || 'Unable to add symbol. Check backend is running on port 5000.', 'error');
    }
  }

  async function patchItem(item: WatchlistItem, payload: Partial<WatchlistItem>) {
    try {
      const response = await updateWatchlistItem(item.symbol, payload);
      globalWatchlistCache = globalWatchlistCache.map((row) => (row.symbol === item.symbol ? response.item : row));
      setItems(globalWatchlistCache);
      setSelected((current) => (current?.symbol === item.symbol ? response.item : current));
    } catch (err: any) {
      toast.push(err?.message || 'Unable to update watchlist symbol', 'error');
    }
  }

  async function removeSymbol(item: WatchlistItem) {
    if (typeof window !== 'undefined' && !window.confirm(`Are you sure you want to remove ${item.symbol} from the watchlist?`)) {
      return;
    }
    const previousCache = globalWatchlistCache;
    const previousSelected = selected;

    globalWatchlistCache = globalWatchlistCache.filter((row) => row.symbol !== item.symbol);
    setItems(globalWatchlistCache);
    setSelected((current) => (current?.symbol === item.symbol ? null : current));

    try {
      await deleteWatchlistItem(item.symbol);
      toast.push(`${item.symbol} removed`, 'success');
    } catch (err: any) {
      globalWatchlistCache = previousCache;
      setItems(previousCache);
      setSelected(previousSelected);
      toast.push(err.response?.data?.message || err?.message || 'Unable to remove symbol', 'error');
    }
  }

  async function pullGrowwStocks() {
    try {
      const { readGrowwResults } = await import('@/lib/growwIntraday');
      let priorityRows = readGrowwResults().priorityRows || [];
      if (!priorityRows.length) {
        toast.push('No cached Groww priority stocks found. Fetching from Groww source...', 'info');
        const payload = await getGrowwIntradayStocks(50);
        const resolvedRows = payload.rows || [];
        const { buildGrowwPriorityRows } = await import('@/lib/growwIntraday');
        priorityRows = buildGrowwPriorityRows(resolvedRows);
      }
      
      const symbols = priorityRows
        .map((r: any) => r.symbol)
        .filter(Boolean);
        
      if (!symbols.length) {
        toast.push('No qualified priority stocks found in Groww source. Run scan on Groww page first.', 'warning');
        return;
      }
      
      const symbolsString = symbols.join(',');
      const response = await addWatchlistItem({
        symbol: symbolsString,
        monitoring_enabled: true,
        alerts_enabled: true,
        notes: 'groww',
      });
      
      if (response.items) {
        globalWatchlistCache = response.items;
        setItems(globalWatchlistCache);
      }
      toast.push(`Successfully imported ${symbols.length} priority stocks from Groww source: ${symbols.join(', ')}`, 'success');
    } catch (err: any) {
      toast.push(err?.message || 'Failed to pull Groww stocks', 'error');
    }
  }

  async function removeSelected() {
    if (!checkedSymbols.length) {
      toast.push('No stocks selected. Check the boxes next to symbols first.', 'warning');
      return;
    }
    if (typeof window !== 'undefined' && !window.confirm(`Are you sure you want to remove all ${checkedSymbols.length} selected stocks?`)) {
      return;
    }
    const previousCache = globalWatchlistCache;
    const previousChecked = checkedSymbols;

    globalWatchlistCache = globalWatchlistCache.filter((row) => !previousChecked.includes(row.symbol));
    setItems(globalWatchlistCache);
    setCheckedSymbols([]);

    try {
      const symbolsString = previousChecked.join(',');
      await deleteWatchlistItem(symbolsString);
      toast.push(`Removed ${previousChecked.length} selected stocks from watchlist`, 'success');
    } catch (err: any) {
      globalWatchlistCache = previousCache;
      setItems(previousCache);
      setCheckedSymbols(previousChecked);
      toast.push(err.response?.data?.message || err?.message || 'Failed to remove selected stocks', 'error');
    }
  }

  async function removeGrowwStocks() {
    const growwSymbols = items
      .filter((row) => row.notes === 'groww' || row.notes?.toLowerCase() === 'groww source')
      .map((row) => row.symbol);
    if (!growwSymbols.length) {
      toast.push('No Groww stocks found in active watchlist', 'info');
      return;
    }
    if (typeof window !== 'undefined' && !window.confirm(`Are you sure you want to remove all ${growwSymbols.length} Groww stocks from the watchlist?`)) {
      return;
    }
    const previousCache = globalWatchlistCache;
    const previousChecked = checkedSymbols;

    globalWatchlistCache = globalWatchlistCache.filter((row) => !growwSymbols.includes(row.symbol));
    setItems(globalWatchlistCache);
    setCheckedSymbols((current) => current.filter((s) => !growwSymbols.includes(s)));

    try {
      const symbolsString = growwSymbols.join(',');
      await deleteWatchlistItem(symbolsString);
      toast.push(`Removed ${growwSymbols.length} Groww stocks from watchlist`, 'success');
    } catch (err: any) {
      globalWatchlistCache = previousCache;
      setItems(previousCache);
      setCheckedSymbols(previousChecked);
      toast.push(err.response?.data?.message || err?.message || 'Failed to remove Groww stocks', 'error');
    }
  }

  async function removeAllWatchlist() {
    if (!items.length) {
      toast.push('Watchlist is already empty', 'info');
      return;
    }
    if (typeof window !== 'undefined' && !window.confirm('Are you sure you want to clear the entire watchlist? This will remove all stocks.')) {
      return;
    }
    const previousCache = globalWatchlistCache;
    const previousChecked = checkedSymbols;

    globalWatchlistCache = [];
    setItems([]);
    setCheckedSymbols([]);

    try {
      const allSymbols = previousCache.map((row) => row.symbol);
      const symbolsString = allSymbols.join(',');
      await deleteWatchlistItem(symbolsString);
      toast.push('Cleared all symbols from watchlist monitor', 'success');
    } catch (err: any) {
      globalWatchlistCache = previousCache;
      setItems(previousCache);
      setCheckedSymbols(previousChecked);
      toast.push(err.response?.data?.message || err?.message || 'Failed to clear watchlist', 'error');
    }
  }

  async function clearAuditHistory() {
    try {
      await clearWatchlistAudit();
      globalAuditCache = [];
      setAuditHistory([]);
      toast.push('Watchlist outcome audit logs cleared', 'success');
    } catch (err: any) {
      toast.push(err?.message || 'Failed to clear audit logs', 'error');
    }
  }

  async function saveGlobalSettings() {
    storeAlertSettingsLocal(settings);
    try {
      const response = await saveAlertSettings(settings);
      const savedSettings = { ...DEFAULT_ALERT_SETTINGS, ...(response.settings || settings) };
      setSettings(savedSettings);
      storeAlertSettingsLocal(savedSettings);
      setSettingsDirty(false);
      toast.push('Alert settings saved', 'success');
    } catch (err: any) {
      toast.push(`${err?.message || 'Unable to sync alert settings to backend.'} Changes remain saved in this browser.`, 'error');
    }
  }

  function updateGlobalSettings(patch: Record<string, any>) {
    setSettings((current) => {
      const nextSettings = { ...current, ...patch };
      storeAlertSettingsLocal(nextSettings);
      return nextSettings;
    });
    setSettingsDirty(true);
  }

  function resetDefaults() {
    const defaults = { ...DEFAULT_ALERT_SETTINGS };
    setSettings(defaults);
    storeAlertSettingsLocal(defaults);
    setSettingsDirty(true);
    toast.push('Suggested alert defaults restored and saved locally.', 'success');
  }

  async function refreshHistory(nextFilters = historyFilters) {
    try {
      const response = await getWatchlistHistory({ ...nextFilters, limit: 100 });
      globalHistoryCache = response.alerts || [];
      setHistory(globalHistoryCache);
    } catch (err: any) {
      toast.push(err?.message || 'Unable to load alert history', 'error');
    }
  }

  async function clearHistory() {
    try {
      await clearWatchlistHistory();
      globalHistoryCache = [];
      setHistory([]);
      toast.push('Watchlist notification log history cleared', 'success');
    } catch (err: any) {
      toast.push(err?.message || 'Failed to clear history log', 'error');
    }
  }

  async function requestDesktopPermission() {
    if (typeof window === 'undefined' || !('Notification' in window)) {
      toast.push('Desktop notifications are not supported in this browser.', 'error');
      return;
    }
    const permission = await Notification.requestPermission();
    toast.push(`Desktop notification permission: ${permission}`, permission === 'granted' ? 'success' : 'error');
  }

  return (
    <main>
      <PageHero
        eyebrow="Watchlist Monitoring"
        title="Watchlist Monitor"
        description="Backend-monitored symbols with strict time, volume, SL, GTT, profit-booking, desktop, and Telegram alert readiness. Manual confirmation required; auto trading disabled."
        actions={<>
          <button className="btn-secondary" type="button" onClick={() => load()}><RefreshCw size={16} /> Refresh</button>
          <button className="btn-secondary" type="button" onClick={requestDesktopPermission}><Bell size={16} /> Browser Alerts</button>
          <button className="btn-secondary" type="button" onClick={() => setShowSettings(!showSettings)}><Settings2 size={16} /> {showSettings ? 'Hide Config' : 'Global Config'}</button>
          <button className="btn-primary" type="button" onClick={saveGlobalSettings}><Save size={16} /> Save Config</button>
        </>}
        metrics={[
          { label: 'Conn', value: connection, tone: connection === 'Live' ? 'good' : 'warn' },
          { label: 'Monitored', value: String(stats.monitored) },
          { label: 'Alerts', value: String(stats.alerts) },
          { label: 'Ready', value: String(stats.tradeReady), tone: stats.tradeReady ? 'good' : 'warn' },
          { label: 'Waiting', value: String(stats.wait), tone: stats.wait ? 'warn' : 'good' },
        ]}
      />

      <div style={{ 
        display: 'flex', 
        flexDirection: 'column', 
        padding: '0 16px', 
        gap: '8px', 
        marginBottom: '10px' 
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase' }}>Add Stock:</span>
          <div className="watchlist-stock-search">
            <input
              value={symbol}
              onChange={(event) => {
                setSymbol(event.target.value.toUpperCase());
                setShowStockSuggestions(true);
              }}
              onFocus={() => setShowStockSuggestions(true)}
              onBlur={() => window.setTimeout(() => setShowStockSuggestions(false), 140)}
              placeholder="RELIANCE, TCS, MTARTECH"
              onKeyDown={(event) => {
                if (event.key === 'Enter') addSymbol();
                if (event.key === 'Escape') setShowStockSuggestions(false);
              }}
              style={{
                padding: '3px 6px',
                fontSize: '0.76rem',
                width: '200px',
                background: 'var(--panel-strong)',
                border: '1px solid var(--border)',
                borderRadius: '4px',
                color: 'var(--text)'
              }}
            />
            {showStockSuggestions && (stockSuggestionsLoading || stockSuggestions.length > 0) && (
              <div className="watchlist-stock-suggestions">
                {stockSuggestionsLoading && <div className="watchlist-stock-suggestion is-muted">Searching...</div>}
                {stockSuggestions.map((stock) => {
                  const displaySymbol = getSearchDisplaySymbol(stock);
                  return (
                    <button
                      className="watchlist-stock-suggestion"
                      key={`${stock.exchange}-${stock.symbol}`}
                      type="button"
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => selectStockSuggestion(stock)}
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
          <button className="btn-primary" type="button" onClick={() => addSymbol()} style={{ padding: '3px 8px', fontSize: '0.72rem', minHeight: '26px' }}><Plus size={11} /> Add Stock</button>
          <button className="btn-secondary" type="button" onClick={resetDefaults} style={{ padding: '3px 8px', fontSize: '0.72rem', minHeight: '26px' }}><RotateCcw size={11} /> Reset Defaults</button>
          <button className="btn-secondary" type="button" onClick={pullGrowwStocks} style={{ padding: '3px 8px', fontSize: '0.72rem', minHeight: '26px' }}><Plus size={11} /> Pull Groww Source</button>
        </div>

        {showSettings && (
          <div style={{
            background: 'var(--surface-3)',
            border: '1px solid var(--border)',
            borderRadius: '6px',
            padding: '10px',
            marginTop: '2px'
          }}>
            <div className="settings-grid compact-settings-grid" style={{ margin: 0, gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '6px' }}>
              {[
                ['min_profit_pct', 'Min Profit %', 'Minimum profit breakout threshold.'],
                ['breakout_distance_pct', 'Breakout Distance %', 'Near resistance alert zone.'],
                ['breakout_volume_multiplier', 'Volume Multiplier', 'BUY volume multiplier.'],
                ['consecutive_candle_count', 'Candle Count', 'Consecutive candle alerts.'],
                ['price_move_pct_threshold', 'Price Move %', 'Single-candle move threshold.'],
                ['price_surge_pct', 'Price Surge %', 'Price surge detection pct.'],
                ['half_percent_move_threshold', 'Half % Move', 'Alert offset step.'],
                ['stop_loss_min_pct', 'SL Min %', 'Minimum stop loss.'],
                ['stop_loss_max_pct', 'SL Max %', 'Maximum risk stop loss.'],
                ['default_stop_loss_pct', 'Default SL %', 'GTT stop loss default.'],
                ['profit_booking_start_pct', 'Book Start %', '50% profit booking start.'],
                ['profit_booking_end_pct', 'Book End %', 'Profit booking zone end.'],
                ['book_partial_quantity_pct', 'Partial Qty %', 'Suggested partial exit qty.'],
                ['cooldown_seconds', 'Cooldown Seconds', 'Alert frequency cooldown.'],
                ['monitoring_interval_seconds', 'Monitor Interval', 'Backend check cycle.'],
              ].map(([key, label, hint]) => (
                <label key={key} style={{ display: 'flex', flexDirection: 'column', gap: '1px', fontSize: '0.65rem', padding: '4px', background: 'rgba(0,0,0,0.15)', border: '1px solid rgba(255,255,255,0.03)', borderRadius: '4px' }}>
                  <span style={{ color: 'var(--muted)', fontWeight: 700 }}>{label}</span>
                  <input 
                    type="number" 
                    value={settings[key] ?? ''} 
                    onChange={(event) => updateGlobalSettings({ [key]: Number(event.target.value) })} 
                    style={{ padding: '2px 4px', fontSize: '0.74rem', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '3px' }}
                  />
                  <small style={{ color: 'var(--muted)', fontSize: '0.6rem' }}>{hint}</small>
                </label>
              ))}
              <label style={{ display: 'flex', flexDirection: 'column', gap: '1px', fontSize: '0.65rem', padding: '4px', background: 'rgba(0,0,0,0.15)', border: '1px solid rgba(255,255,255,0.03)', borderRadius: '4px' }}>
                <span style={{ color: 'var(--muted)', fontWeight: 700 }}>First Window Ends</span>
                <input type="time" value={settings.first_30_minutes_wait_until ?? '09:45'} onChange={(event) => updateGlobalSettings({ first_30_minutes_wait_until: event.target.value })} style={{ padding: '2px 4px', fontSize: '0.74rem', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '3px' }} />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '1px', fontSize: '0.65rem', padding: '4px', background: 'rgba(0,0,0,0.15)', border: '1px solid rgba(255,255,255,0.03)', borderRadius: '4px' }}>
                <span style={{ color: 'var(--muted)', fontWeight: 700 }}>Confirm After</span>
                <input type="time" value={settings.confirmation_wait_until ?? '11:00'} onChange={(event) => updateGlobalSettings({ confirmation_wait_until: event.target.value })} style={{ padding: '2px 4px', fontSize: '0.74rem', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '3px' }} />
              </label>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', marginTop: '8px', fontSize: '0.7rem', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '6px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={settings.watchlist_monitoring_enabled !== false} onChange={(event) => updateGlobalSettings({ watchlist_monitoring_enabled: event.target.checked })} /> Monitoring</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={settings.groww_source_enabled !== false} onChange={(event) => updateGlobalSettings({ groww_source_enabled: event.target.checked })} /> Fetch from Groww</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={Boolean(settings.auto_add_candidates)} onChange={(event) => updateGlobalSettings({ auto_add_candidates: event.target.checked })} /> Auto-Add Scanned Candidates</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={settings.no_breakout_first_30_minutes !== false} onChange={(event) => updateGlobalSettings({ no_breakout_first_30_minutes: event.target.checked })} /> No BUY First 30m</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={settings.wait_until_11am_confirmation !== false} onChange={(event) => updateGlobalSettings({ wait_until_11am_confirmation: event.target.checked })} /> Wait Until 11 AM</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={settings.gtt_plan_enabled !== false} onChange={(event) => updateGlobalSettings({ gtt_plan_enabled: event.target.checked })} /> GTT Plan</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={settings.avoid_negative_alerts !== false} onChange={(event) => updateGlobalSettings({ avoid_negative_alerts: event.target.checked })} /> Filter Negative Alerts</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={Boolean(settings.market_hours_only)} onChange={(event) => updateGlobalSettings({ market_hours_only: event.target.checked })} /> Market Hours Only</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={settings.desktop_enabled !== false} onChange={(event) => updateGlobalSettings({ desktop_enabled: event.target.checked })} /> Desktop Alerts</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={Boolean(settings.sound_enabled)} onChange={(event) => updateGlobalSettings({ sound_enabled: event.target.checked })} /> Alert Sound</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={Boolean(settings.telegram_enabled)} onChange={(event) => updateGlobalSettings({ telegram_enabled: event.target.checked })} /> Telegram Alerts</label>
            </div>
            <div style={{ fontSize: '0.65rem', color: 'var(--muted)', marginTop: '6px', display: 'flex', alignItems: 'center', gap: '4px' }}><ShieldCheck size={12} /> Manual confirmation required. Auto buy/sell is disabled; use Groww GTT manually for Target/SL.</div>
          </div>
        )}
      </div>

      <TerminalPanel eyebrow="Active Signals" title="High-Profitable Trade Suggestions">
        <div className="terminal-table" style={{ overflowX: 'auto', width: '100%', marginBottom: '20px' }}>
          <div className="terminal-table-head" style={{ display: 'grid', gridTemplateColumns: '180px 80px 90px 130px 90px 100px 100px 80px 80px 100px 80px', minWidth: '1110px' }}>
            {['Symbol', 'Direction', 'Price', 'Suggested Time', 'Entry', 'Return %', 'Trailing Stop', 'Target 1', 'Target 2', 'Status', 'Actions'].map((heading, i) => (
              <span key={i}>{heading}</span>
            ))}
          </div>
          <div style={{ minWidth: '1110px' }}>
            {activeSuggestions.length === 0 ? (
              <div style={{ padding: '24px', textAlign: 'center', color: 'var(--muted)', fontSize: '0.82rem', background: 'rgba(255, 255, 255, 0.01)' }}>
                No active trade suggestions at this time.
              </div>
            ) : (
              activeSuggestions.map((item) => {
                const isSelectedActive = selectedActiveSignal === item.symbol;
                const snap = item.snapshot || {};
                const direction = String(snap.direction || 'BUY').toUpperCase();
                const pl = snap.current_gain_loss_percent ?? 0.0;
                const plClass = pl >= 0 ? 'positive' : 'negative';
                const liveTick = quotes[item.symbol];
                const currentPrice = liveTick ? liveTick.price : snap.current_price;
                const isBuy = direction !== 'SELL';
                const rowBg = isBuy ? 'rgba(20, 184, 166, 0.05)' : 'rgba(244, 63, 94, 0.05)';
                return (
                  <React.Fragment key={item.symbol}>
                    <div 
                      className={`terminal-table-row ${isSelectedActive ? 'is-selected' : ''}`} 
                      onClick={() => setSelectedActiveSignal(isSelectedActive ? null : item.symbol)}
                      style={{ 
                        display: 'grid',
                        gridTemplateColumns: '180px 80px 90px 130px 90px 100px 100px 80px 80px 100px 80px',
                        alignItems: 'center',
                        padding: '6px 12px',
                        borderBottom: '1px solid rgba(255,255,255,0.04)',
                        background: rowBg,
                        cursor: 'pointer',
                        fontSize: '0.78rem'
                      }}
                    >
                      <strong style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                        <span style={{ color: 'var(--accent)', fontSize: '0.82rem', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>{snap.company_name || item.company_name}</span>
                        <span style={{ fontSize: '0.72rem', color: 'var(--muted)', fontWeight: 'bold' }}>{item.symbol}</span>
                      </strong>
                      <span>
                        <span className={`pill pill-${isBuy ? 'good' : 'bad'}`} style={{ fontWeight: 'bold' }}>
                          {direction}
                        </span>
                      </span>
                      <span>{formatCurrency(currentPrice)}</span>
                      <span style={{ color: 'var(--text-bright)', fontWeight: '500' }}>
                        {snap.suggested_at || '-'}
                      </span>
                      <span>{formatCurrency(snap.suggested_entry_price || snap.entry)}</span>
                      <span className={plClass} style={{ fontWeight: 'bold' }}>
                        {pl >= 0 ? '+' : ''}{pl.toFixed(2)}%
                      </span>
                      <span style={{ color: '#ffbd59', fontWeight: 'bold' }}>{formatCurrency(snap.trailingStop || snap.stop_loss)}</span>
                      <span>{formatCurrency(snap.target1)}</span>
                      <span>{formatCurrency(snap.target2)}</span>
                      <span>
                        <span className={`pill pill-${statusTone(snap.suggestion_status || 'ACTIVE')}`} style={{ textTransform: 'uppercase', fontSize: '0.68rem', fontWeight: 'bold' }}>
                          {snap.suggestion_status || 'ACTIVE'}
                        </span>
                      </span>
                      <span>
                        <button
                          className="btn-secondary"
                          type="button"
                          onClick={async (e) => {
                            e.stopPropagation();
                            if (confirm(`Are you sure you want to close the trade signal for ${item.symbol}?`)) {
                              try {
                                await closeSignal(item.symbol);
                                toast.push(`Closed trade suggestion for ${item.symbol}`, 'success');
                                load(); // reload watchlist items
                              } catch (err: any) {
                                toast.push(`Failed to close trade suggestion: ${err.message}`, 'error');
                              }
                            }
                          }}
                          style={{
                            padding: '2px 8px',
                            fontSize: '0.7rem',
                            minHeight: '22px',
                            background: 'rgba(255, 100, 100, 0.1)',
                            color: '#ff6b6b',
                            border: '1px solid rgba(255, 100, 100, 0.2)',
                            borderRadius: '4px',
                            cursor: 'pointer'
                          }}
                        >
                          Close
                        </button>
                      </span>
                    </div>
                    {isSelectedActive && (
                      <StockDetailsPanel
                        item={item}
                        snap={snap}
                        currentPrice={currentPrice}
                        pinnedSymbols={pinnedSymbols}
                        togglePinSymbol={togglePinSymbol}
                        patchItem={patchItem}
                        removeSymbol={removeSymbol}
                        onClose={() => setSelectedActiveSignal(null)}
                        minWidth="1110px"
                      />
                    )}
                  </React.Fragment>
                );
              })
            )}
          </div>
        </div>
      </TerminalPanel>

      <TerminalPanel eyebrow="Live Table" title="Watched Stocks">
        {error && <div className="status-banner danger">{error}<button type="button" onClick={() => load()}>Retry</button></div>}
        {items.length ? (
          <>
            <div className="watchlist-live-toolbar">
              <div className="watchlist-live-actions">
                <label className="watchlist-live-select-all">
                  <input
                    type="checkbox"
                    checked={filteredItems.length > 0 && checkedSymbols.length === filteredItems.length}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setCheckedSymbols(filteredItems.map(item => item.symbol));
                      } else {
                        setCheckedSymbols([]);
                      }
                    }}
                  />
                  <span>Select All ({checkedSymbols.length} / {filteredItems.length})</span>
                </label>
                <button
                  className="btn-secondary"
                  type="button"
                  onClick={removeSelected}
                  disabled={!checkedSymbols.length}
                  style={{ opacity: checkedSymbols.length ? 1 : 0.6 }}
                >
                  Remove Selected
                </button>
                <button
                  className="btn-secondary"
                  type="button"
                  onClick={removeGrowwStocks}
                >
                  Remove Groww Stocks
                </button>
                <button
                  className="btn-secondary"
                  type="button"
                  onClick={removeAllWatchlist}
                  style={{ background: 'rgba(255,100,100,0.05)', color: '#ff6b6b', border: '1px solid rgba(255,100,100,0.15)' }}
                >
                  Remove All
                </button>
              </div>

              <div className="watchlist-live-view-controls">
                <button className="btn-secondary" type="button" onClick={() => setShowLiveFilters((value) => !value)}>
                  <SlidersHorizontal size={13} /> {showLiveFilters ? 'Hide Filters' : 'Show Filters'}
                </button>
                <span>Show:</span>
                <select
                  value={displayLimit}
                  onChange={(e) => setDisplayLimit(e.target.value === 'all' ? 'all' : Number(e.target.value))}
                >
                  <option value={5}>Top 5</option>
                  <option value={10}>Top 10</option>
                  <option value={20}>Top 20</option>
                  <option value={30}>Top 30</option>
                  <option value={40}>Top 40</option>
                  <option value={50}>Top 50</option>
                  <option value="all">All</option>
                </select>
              </div>
            </div>

            {showLiveFilters && (
              <div className="watchlist-live-filters">
                <input placeholder="Symbol or company" value={filterQuery} onChange={(event) => setFilterQuery(event.target.value)} />
                <input placeholder="Readiness" value={filterReadiness} onChange={(event) => setFilterReadiness(event.target.value)} />
                <input placeholder="Action" value={filterAction} onChange={(event) => setFilterAction(event.target.value)} />
                <select value={filterDirection} onChange={(event) => setFilterDirection(event.target.value)}>
                  <option value="all">All Signals</option>
                  <option value="buy_opp">Buy Opp.</option>
                  <option value="sell_opp">Sell Opp.</option>
                  <option value="buy_ready">Buy Ready</option>
                  <option value="sell_ready">Sell Ready</option>
                  <option value="wait">Waiting</option>
                  <option value="avoid">Avoid</option>
                  <option value="high_alert">High Alert</option>
                </select>
                <select value={filterAlerts} onChange={(event) => setFilterAlerts(event.target.value)}>
                  <option value="">Alerts All</option>
                  <option value="on">Alerts On</option>
                  <option value="off">Alerts Off</option>
                </select>
                <select value={filterSource} onChange={(event) => setFilterSource(event.target.value)}>
                  <option value="all">Source All</option>
                  <option value="custom">Custom</option>
                  <option value="groww">Groww</option>
                </select>
                <button
                  className="btn-secondary"
                  type="button"
                  onClick={() => {
                    setFilterQuery('');
                    setFilterReadiness('');
                    setFilterAction('');
                    setFilterAlerts('');
                    setFilterSource('all');
                    setFilterDirection('all');
                  }}
                >
                  Reset
                </button>
              </div>
            )}

            {filteredItems.length ? (
              <div className="terminal-table watchlist-monitor-table">
                 <div className="terminal-table-head" style={{ display: 'grid', gridTemplateColumns: '50px 180px 80px 70px 70px 80px 80px 70px 100px 120px 130px' }}>
                   {['', 'Symbol', 'Price', 'Change %', 'Vol vs Avg', 'Breakout', 'Resistance', 'Distance', 'Status', 'Suggested Time', 'Last Alert'].map((heading, i) => (
                     <span key={i} style={{ fontWeight: 'bold' }}>{heading}</span>
                   ))}
                 </div>
                {filteredItems.slice(0, displayLimit === 'all' ? undefined : displayLimit).map((item) => {
                  const isSelected = selected?.symbol === item.symbol;
                  const snap = item.snapshot || {};
                  const liveTick = quotes[item.symbol];
                  const currentPrice = liveTick ? liveTick.price : snap.current_price;
                  return (
                    <React.Fragment key={item.symbol}>
                      <WatchlistRow
                        item={item}
                        isSelected={isSelected}
                        onClick={() => setSelected(isSelected ? null : item)}
                        checkedSymbols={checkedSymbols}
                        setCheckedSymbols={setCheckedSymbols}
                        pinnedSymbols={pinnedSymbols}
                        togglePinSymbol={togglePinSymbol}
                        patchItem={patchItem}
                        removeSymbol={removeSymbol}
                      />

                      {isSelected && (
                        <StockDetailsPanel
                          item={item}
                          snap={snap}
                          currentPrice={currentPrice}
                          pinnedSymbols={pinnedSymbols}
                          togglePinSymbol={togglePinSymbol}
                          patchItem={patchItem}
                          removeSymbol={removeSymbol}
                          onClose={() => setSelected(null)}
                          minWidth="1030px"
                        />
                      )}
                    </React.Fragment>
                  );
                })}
              </div>
            ) : (
              <div className="empty-state">No matching stocks found.</div>
            )}
          </>
        ) : (
          <div className="empty-state">No stocks in watchlist. Add a symbol above to start monitoring.</div>
        )}
      </TerminalPanel>

      <TerminalPanel 
        eyebrow="Watchlist Audit" 
        title="Watchlist Outcomes & Comparison"
        actions={
          <button 
            className="btn-secondary" 
            type="button" 
            onClick={clearAuditHistory} 
            disabled={!auditHistory.length || loadingAudit}
          >
            Clear Outcomes
          </button>
        }
      >
        {auditError ? (
          <div className="status-banner danger">
            {auditError}
            <button type="button" onClick={() => load()}>Retry</button>
          </div>
        ) : loadingAudit ? (
          <div className="empty-state">Loading watchlist outcomes...</div>
        ) : (
          <DataTable
            columns={['Symbol', 'Outcome', 'Net Profit %', 'Entry Price', 'Exit Price', 'Target 1', 'Stop Loss', 'Suggested Time', 'Closed At', 'Details']}
            rows={auditHistory.map((row, index) => [
              <strong key={`${row.symbol}-${index}`}>{row.symbol}</strong>,
              <span key={`${row.symbol}-status-${index}`} className={`status-badge ${row.outcome === 'Target Hit' ? 'status-good' : 'status-bad'}`}>
                {row.outcome === 'Target Hit' ? 'TARGET HIT' : 'STOPLOSS HIT'}
              </span>,
              <span key={`${row.symbol}-pnl-${index}`} className={row.profit_loss_pct >= 0 ? 'positive' : 'negative'} style={{ fontWeight: 'bold' }}>
                {row.profit_loss_pct >= 0 ? `+${row.profit_loss_pct.toFixed(2)}%` : `${row.profit_loss_pct.toFixed(2)}%`}
              </span>,
              row.entry_price ? `INR ${row.entry_price.toFixed(2)}` : '-',
              row.exit_price ? `INR ${row.exit_price.toFixed(2)}` : '-',
              row.target1 ? `INR ${row.target1.toFixed(2)}` : '-',
              row.stop_loss ? `INR ${row.stop_loss.toFixed(2)}` : '-',
              row.suggested_time || '-',
              row.archived_at ? new Date(row.archived_at).toLocaleString('en-IN') : '-',
              row.hit_details || row.trade_reason || '-',
            ])}
            emptyTitle="No completed watchlist outcomes"
            emptyBody="When a monitored stock hits its target or stoploss price, it will be automatically moved here for performance auditing."
          />
        )}
      </TerminalPanel>

      <TerminalPanel
        eyebrow="Alert History"
        title="Watchlist Notification Log"
        className="watchlist-history-panel"
        actions={
          <div style={{ display: 'flex', gap: '8px' }}>
            <button className="btn-secondary" type="button" onClick={() => refreshHistory()}>
              <History size={16} /> Refresh History
            </button>
            <button 
              className="btn-secondary" 
              type="button" 
              onClick={async () => {
                if (confirm('Are you sure you want to clear all notification alert history?')) {
                  await clearHistory();
                }
              }}
              style={{ background: 'rgba(255, 100, 100, 0.1)', color: '#ff6b6b', border: '1px solid rgba(255, 100, 100, 0.2)' }}
            >
              <Trash2 size={16} /> Clear History
            </button>
          </div>
        }
      >
        <div className="watchlist-history-filters">
          <input placeholder="Symbol" value={historyFilters.symbol || ''} onChange={(event) => setHistoryFilters((current) => ({ ...current, symbol: event.target.value.toUpperCase() }))} />
          <input placeholder="Alert type" value={historyFilters.alert_type || ''} onChange={(event) => setHistoryFilters((current) => ({ ...current, alert_type: event.target.value.toUpperCase() }))} />
          <input placeholder="Action" value={historyFilters.action || ''} onChange={(event) => setHistoryFilters((current) => ({ ...current, action: event.target.value.toUpperCase() }))} />
          <input type="date" value={historyFilters.date || ''} onChange={(event) => setHistoryFilters((current) => ({ ...current, date: event.target.value }))} />
          <select value={historyFilters.telegram_sent || ''} onChange={(event) => setHistoryFilters((current) => ({ ...current, telegram_sent: event.target.value }))}>
            <option value="">Telegram All</option>
            <option value="true">Telegram Sent</option>
            <option value="false">Telegram Not Sent</option>
          </select>
          <select value={historyFilters.trade_taken || ''} onChange={(event) => setHistoryFilters((current) => ({ ...current, trade_taken: event.target.value }))}>
            <option value="">Trade All</option>
            <option value="true">Taken</option>
            <option value="false">Not Taken</option>
          </select>
          <button className="btn-secondary" type="button" onClick={() => refreshHistory()}>Apply</button>
        </div>
        {history.length ? (
          <div className="terminal-table alert-history-table">
            <div className="terminal-table-head">
              {['Time', 'Symbol', 'Type', 'Action', 'Price', 'Entry', 'SL', 'Targets', 'Volume', 'Reason', 'Telegram', 'Desktop'].map((heading) => <span key={heading}>{heading}</span>)}
            </div>
            {history.map((alert) => {
              const act = String(alert.action || '').toUpperCase();
              const isBuyAlert = act.includes('BUY') || act.includes('BOOK') || act.includes('TRAIL') || act.includes('TARGET');
              const isSellAlert = act.includes('SELL') || act.includes('AVOID') || act.includes('EXIT') || act.includes('STOP') || act.includes('LOSS');
              const rowBg = isBuyAlert ? 'rgba(20, 184, 166, 0.05)' : isSellAlert ? 'rgba(244, 63, 94, 0.05)' : undefined;
              return (
                <article key={alert.alert_id} className="terminal-table-row alert-history-row" style={{ background: rowBg }}>
                  <span>{formatTime(alert.created_at)}</span>
                  <strong>{alert.symbol}<small>{alert.severity}</small></strong>
                  <span>{alert.alert_type}</span>
                  <span className={`pill pill-${actionTone(alert.action)}`}>{alert.action || '-'}</span>
                  <span>{formatCurrency(alert.trigger_price)}</span>
                  <span>{formatCurrency(alert.entry)}</span>
                  <span>{formatCurrency(alert.stop_loss)}</span>
                  <span>{[alert.target1, alert.target2].filter(Boolean).map(formatCurrency).join(' / ') || '-'}</span>
                  <span>{alert.volume_ratio ? `${formatNumber(alert.volume_ratio)}x` : '-'}</span>
                  <span>{alert.reason || alert.message || '-'}</span>
                  <span>{alert.telegram_sent ? 'Sent' : 'No'}</span>
                  <span>{desktopDeliveryLabel(alert)}</span>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="empty-state">No watchlist alerts yet. Alerts will appear after backend rules trigger.</div>
        )}
      </TerminalPanel>

    </main>
  );
}
