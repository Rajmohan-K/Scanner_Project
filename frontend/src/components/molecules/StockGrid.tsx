"use client";
import React, { memo, useEffect, useMemo, useState } from 'react';
import { ArrowLeft, ArrowRight, ArrowRightLeft, BarChart3, BellPlus, FileDown, GitCompare, Pin, Star, Telescope } from 'lucide-react';
import { useDispatch } from 'react-redux';
import { addSymbol } from '@/state/watchlistSlice';
import { addV20WatchlistItem } from '@/lib/api';
import { StockRecord } from './StockCard';
import Skeleton from '@/components/atoms/Skeleton';
import { EmptyState } from '@/components/terminal/TerminalPrimitives';
import { useToast } from '@/components/layout/ToastProvider';
import { addStocksToLiveMonitor } from '@/lib/liveMonitor';

const dash = '-';
const allColumns = [
  'Symbol',
  'Sector',
  'LTP',
  'Entry',
  'SL',
  'Targets',
  'Profit',
  'Scores',
  'Signal',
  'Reason',
  'Updated',
  'Actions',
] as const;
type ColumnKey = typeof allColumns[number];
type DensityMode = 'compact' | 'comfortable' | 'analyst' | 'executive';
type StockGridProps = {
  items: StockRecord[];
  loading?: boolean;
  onReorder?: (items: StockRecord[]) => void;
  pageSize?: number;
  onPinStock?: (item: StockRecord) => void;
  pinLabel?: string;
};

const signalOptions = ['All', 'Strong Buy', 'Buy', 'Watch', 'Hold', 'Avoid', 'No Trade'];

function formatPrice(value?: number) {
  if (typeof value !== 'number') return dash;
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(value);
}

function formatScore(value?: number) {
  if (typeof value !== 'number') return dash;
  if (Math.abs(value) <= 1) return `${Math.round(value * 100)}%`;
  return `${Math.round(value)}%`;
}

function pushSymbolToScanner(target: 'intraday' | 'swing', symbol: string) {
  if (typeof window === 'undefined' || !symbol || symbol === dash) return;
  const key = `custom-${target}-symbols`;
  const existing = window.localStorage.getItem(key) || '';
  const symbols = existing
    .split(/[\s,]+/)
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean);
  const next = Array.from(new Set([symbol.toUpperCase(), ...symbols]));
  window.localStorage.setItem(key, next.join(', '));
  window.dispatchEvent(new CustomEvent('custom-scanner-symbols', { detail: { target, symbols: next } }));
}

function exportRows(rows: StockRecord[]) {
  const headers = ['symbol', 'sector', 'live_price', 'entry_price', 'stop_loss', 'target1', 'target2', 'target3', 'expected_return', 'stop_distance_pct', 'ml_score', 'confidence_pct', 'action', 'reason'];
  const csv = [
    headers.join(','),
    ...rows.map((row) => headers.map((key) => JSON.stringify((row as any)[key] ?? '')).join(',')),
  ].join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `scanner-v20-grid-${Date.now()}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

function exportSingleRow(row: StockRecord) {
  exportRows([row]);
}

function signalOf(item: StockRecord) {
  const raw = String(
    (item as any).action ||
    (item as any).signal ||
    (item as any).trade_type ||
    (item as any).premarket_action ||
    (item as any).final_decision ||
    'WATCH',
  );
  return raw.replace(/_/g, ' ').trim().toUpperCase() || 'WATCH';
}

function addToCompare(symbol: string) {
  if (typeof window === 'undefined') return;
  const key = 'v20-compare-symbols';
  const existing = (window.localStorage.getItem(key) || '').split(',').map((item) => item.trim()).filter(Boolean);
  const next = Array.from(new Set([symbol, ...existing])).slice(0, 8);
  window.localStorage.setItem(key, next.join(','));
  window.dispatchEvent(new CustomEvent('v20-compare-updated', { detail: { symbols: next } }));
}

function openChart(symbol: string) {
  if (typeof window === 'undefined') return;
  window.open(`${process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:5000'}/api/candlestick?stock=${encodeURIComponent(symbol)}&days=90&interval=1d`, '_blank', 'noopener,noreferrer');
}

function openReportExport() {
  if (typeof window === 'undefined') return;
  window.open(`${process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:5000'}/api/export/watchlist?horizon=intraday`, '_blank', 'noopener,noreferrer');
}

function StockGridComponent({
  items,
  loading = false,
  onReorder,
  pageSize = 25,
  onPinStock,
  pinLabel = 'Pin to watchlist',
}: StockGridProps) {
  const dispatch = useDispatch();
  const toast = useToast();
  const [localItems, setLocalItems] = useState<StockRecord[]>(items || []);
  const [page, setPage] = useState(1);
  const [sortKey, setSortKey] = useState<keyof StockRecord>('expected_return');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [density, setDensity] = useState<DensityMode>('analyst');
  const [signalFilter, setSignalFilter] = useState('All');
  const [selectedStock, setSelectedStock] = useState<StockRecord | null>(null);
  const [visibleColumns, setVisibleColumns] = useState<Record<ColumnKey, boolean>>(() => Object.fromEntries(allColumns.map((column) => [column, true])) as Record<ColumnKey, boolean>);

  useEffect(() => {
    setLocalItems(items || []);
    setPage(1);
  }, [items]);

  const filteredItems = useMemo(() => {
    if (signalFilter === 'All') return localItems;
    const target = signalFilter.toUpperCase();
    return localItems.filter((item) => {
      const signal = signalOf(item);
      if (target === 'BUY') return /\bBUY\b/.test(signal);
      if (target === 'WATCH') return signal.includes('WATCH');
      if (target === 'AVOID') return signal.includes('AVOID') || signal.includes('REJECT');
      if (target === 'NO TRADE') return signal.includes('NO TRADE') || signal.includes('NO-TRADE');
      return signal === target;
    });
  }, [localItems, signalFilter]);

  const sortedItems = useMemo(() => {
    const copy = Array.from(filteredItems);
    copy.sort((a: any, b: any) => {
      const left = a[sortKey];
      const right = b[sortKey];
      const leftValue = typeof left === 'number' ? left : String(left ?? '').toLowerCase();
      const rightValue = typeof right === 'number' ? right : String(right ?? '').toLowerCase();
      if (leftValue < rightValue) return sortDirection === 'asc' ? -1 : 1;
      if (leftValue > rightValue) return sortDirection === 'asc' ? 1 : -1;
      return 0;
    });
    return copy;
  }, [filteredItems, sortDirection, sortKey]);
  const effectivePageSize = density === 'compact' ? 40 : density === 'executive' ? 12 : pageSize;
  const pageCount = Math.max(1, Math.ceil(sortedItems.length / effectivePageSize));
  useEffect(() => {
    setPage((current) => Math.min(current, pageCount));
  }, [pageCount]);
  const visibleItems = useMemo(() => {
    const start = (page - 1) * effectivePageSize;
    return sortedItems.slice(start, start + effectivePageSize);
  }, [effectivePageSize, page, sortedItems]);

  function onDragStart(e: React.DragEvent, idx: number) {
    e.dataTransfer.setData('text/plain', String(idx));
    e.dataTransfer.effectAllowed = 'move';
  }

  function onDrop(e: React.DragEvent, idx: number) {
    e.preventDefault();
    const from = Number(e.dataTransfer.getData('text/plain'));
    if (Number.isNaN(from)) return;
    const copy = Array.from(localItems);
    const [moved] = copy.splice(from, 1);
    copy.splice(idx, 0, moved);
    setLocalItems(copy);
    onReorder?.(copy);
  }

  if (loading) {
    return (
      <div className="stock-list-skeleton">
        {Array.from({ length: 8 }).map((_, idx) => (
          <Skeleton key={idx} width="100%" height={44} />
        ))}
      </div>
    );
  }

  if (!localItems.length) {
    return <EmptyState title="No saved scan results yet" body="Backend is online. Run a scan from Scan Center to populate this table with live results." />;
  }

  function toggleSort(key: keyof StockRecord) {
    if (sortKey === key) {
      setSortDirection((value) => value === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortDirection('desc');
    }
  }

  function column(label: ColumnKey, content: React.ReactNode) {
    return visibleColumns[label] ? content : null;
  }

  function compactReason(item: StockRecord) {
    const text = String(item.pattern || item.reason || item.quality_filter_reasons || dash);
    if (!text || text === dash) return dash;
    return text.split('|').map((part) => part.trim()).filter(Boolean)[0] || text;
  }

  function fullReason(item: StockRecord) {
    return [item.pattern, item.reason || item.quality_filter_reasons].filter(Boolean).join(' | ') || 'No backend reason returned.';
  }

  async function pinToWatchlist(symbol: string) {
    if (!symbol || symbol === dash) return;
    try {
      await addV20WatchlistItem(symbol);
      dispatch(addSymbol(symbol));
      toast?.push(`${symbol} added to watchlist`, 'success');
    } catch {
      toast?.push(`Unable to add ${symbol} to watchlist`, 'error');
    }
  }

  function addToDashboardMonitor(item: StockRecord) {
    const symbol = item.symbol || item.stock || dash;
    if (!symbol || symbol === dash) return;
    const result = addStocksToLiveMonitor([item], 'stock-grid');
    const action = result.added ? 'added to' : 'updated in';
    toast?.push(`${symbol} ${action} dashboard live monitor`, 'success');
  }

  async function handlePrimaryPin(item: StockRecord) {
    if (onPinStock) {
      onPinStock(item);
      return;
    }
    const symbol = item.symbol || item.stock || dash;
    await pinToWatchlist(symbol);
  }

  return (
    <div className={`stock-list-table stock-list-table--${density}`} role="table" aria-label="Live stock results">
      <div className="data-grid-toolbar">
        <div>
          <strong>Version 20 Data Grid</strong>
          <span>{sortedItems.length} visible / {localItems.length} analyzed stocks</span>
        </div>
        <div className="data-grid-controls">
          <select value={signalFilter} onChange={(event) => setSignalFilter(event.target.value)}>
            {signalOptions.map((option) => <option key={option} value={option}>{option === 'All' ? 'All signals' : option}</option>)}
          </select>
          <select value={String(sortKey)} onChange={(event) => setSortKey(event.target.value as keyof StockRecord)}>
            <option value="expected_return">Expected Profit</option>
            <option value="ml_score">ML Score</option>
            <option value="confidence_pct">Confidence</option>
            <option value="data_reliability_score">Data Quality</option>
            <option value="rrr">Risk Reward</option>
            <option value="live_price">Live Price</option>
          </select>
          <select value={density} onChange={(event) => setDensity(event.target.value as DensityMode)}>
            <option value="compact">Compact</option>
            <option value="comfortable">Comfortable</option>
            <option value="analyst">Analyst</option>
            <option value="executive">Executive</option>
          </select>
          <button className="btn-secondary" type="button" onClick={() => exportRows(sortedItems)}><FileDown size={15} /> CSV</button>
        </div>
        <div className="column-toggle-row">
          {allColumns.filter((columnName) => !['Symbol', 'Actions'].includes(columnName)).map((columnName) => (
            <label key={columnName}>
              <input type="checkbox" checked={visibleColumns[columnName]} onChange={(event) => setVisibleColumns((current) => ({ ...current, [columnName]: event.target.checked }))} />
              <span>{columnName}</span>
            </label>
          ))}
        </div>
      </div>
      <div className="stock-grid-content">
      <div className="stock-grid-rows">
      <div className="stock-list-row stock-list-head" role="row">
        {column('Symbol', <span><button type="button" onClick={() => toggleSort('symbol')}>Symbol</button></span>)}
        {column('Sector', <span>Sector</span>)}
        {column('LTP', <span><button type="button" onClick={() => toggleSort('live_price')}>LTP</button></span>)}
        {column('Entry', <span>Entry</span>)}
        {column('SL', <span>SL</span>)}
        {column('Targets', <span>Targets</span>)}
        {column('Profit', <span><button type="button" onClick={() => toggleSort('expected_return')}>Profit / Quality</button></span>)}
        {column('Scores', <span><button type="button" onClick={() => toggleSort('ml_score')}>Scores</button></span>)}
        {column('Signal', <span>Signal</span>)}
        {column('Reason', <span>Pattern / Reason</span>)}
        {column('Updated', <span>Updated</span>)}
        {column('Actions', <span>Actions</span>)}
      </div>
      {!visibleItems.length && (
        <div className="stock-grid-empty">
          No stocks match the selected signal filter.
        </div>
      )}
      {visibleItems.map((item, idx) => {
        const absoluteIndex = (page - 1) * effectivePageSize + idx;
        const symbol = item.symbol || item.stock || dash;
        const action = signalOf(item);
        const selected = selectedStock && (selectedStock.symbol || selectedStock.stock) === symbol;
        return (
          <React.Fragment key={`${symbol}-${idx}`}>
          <div
            className={`stock-list-row ${selected ? 'is-selected' : ''}`}
            role="row"
            draggable
            onClick={() => setSelectedStock(item)}
            onDragStart={(e) => onDragStart(e, absoluteIndex)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => onDrop(e, absoluteIndex)}
          >
            {column('Symbol', <span data-label="Symbol"><strong>{symbol}</strong><small>{item.stock || dash}</small></span>)}
            {column('Sector', <span data-label="Sector">{item.sector || dash}<small>{item.industry || ''}</small></span>)}
            {column('LTP', <span data-label="LTP" className="mono">INR {formatPrice(item.live_price)}</span>)}
            {column('Entry', <span data-label="Entry" className="mono">{formatPrice(item.entry_price)}</span>)}
            {column('SL', <span data-label="SL" className="mono">{formatPrice(item.stop_loss)}</span>)}
            {column('Targets', <span data-label="Targets" className="mono">{formatPrice(item.target1)} / {formatPrice(item.target2)} / {formatPrice(item.target3)}</span>)}
            {column('Profit', <span data-label="Profit"><small className="heat-good">Exp {typeof item.expected_return === 'number' ? `${item.expected_return.toFixed(1)}%` : dash}</small><small>Stop {typeof item.stop_distance_pct === 'number' ? `${item.stop_distance_pct.toFixed(1)}%` : dash}</small><small>Data {formatScore(item.data_reliability_score)}</small></span>)}
            {column('Scores', <span data-label="Scores"><small>ML {formatScore(item.ml_score)}</small><small>Tech {formatScore(item.technical_score)}</small><small>Conf {formatScore(item.confidence_pct)}</small></span>)}
            {column('Signal', <span data-label="Signal"><b className={`signal-pill signal-pill--${action.toLowerCase().replace(/\s+/g, '-')}`}>{action}</b><small>RR {item.rrr || dash}</small></span>)}
            {column('Reason', <span data-label="Pattern / Reason" className="reason-cell">
              <button type="button" onClick={(event) => { event.stopPropagation(); setSelectedStock(item); }}>
                {compactReason(item)}
              </button>
              <small>Hover / select</small>
              <em>{fullReason(item)}</em>
            </span>)}
            {column('Updated', <span data-label="Updated">{item.last_updated || dash}<small>{item.generated_at || ''}</small></span>)}
            {column('Actions', <span data-label="Actions" className="row-actions">
              <button className="icon-button" title={pinLabel} type="button" onClick={(event) => { event.stopPropagation(); handlePrimaryPin(item); }}><Pin size={15} /></button>
              <button className="icon-button" title="Add to dashboard live monitor" type="button" onClick={(event) => { event.stopPropagation(); addToDashboardMonitor(item); }}><BellPlus size={15} /></button>
              <button className="icon-button" title="Push to intraday custom scan" type="button" onClick={(event) => { event.stopPropagation(); pushSymbolToScanner('intraday', symbol); }}><ArrowRightLeft size={15} /></button>
              <button className="icon-button" title="Push to swing custom scan" type="button" onClick={(event) => { event.stopPropagation(); pushSymbolToScanner('swing', symbol); }}><Star size={15} /></button>
              <button className="icon-button" title="Add to compare" type="button" onClick={(event) => { event.stopPropagation(); addToCompare(symbol); }}><GitCompare size={15} /></button>
              <button className="icon-button" title="Open detailed analysis JSON" type="button" onClick={(event) => { event.stopPropagation(); openChart(symbol); }}><Telescope size={15} /></button>
              <button className="icon-button" title="Export this row" type="button" onClick={(event) => { event.stopPropagation(); exportSingleRow(item); }}><FileDown size={15} /></button>
              <button className="icon-button" title="Export watchlist report" type="button" onClick={(event) => { event.stopPropagation(); openReportExport(); }}><BarChart3 size={15} /></button>
            </span>)}
          </div>
          {selected && (
            <div className="selected-stock-detail selected-stock-detail--inline">
              <div>
                <span>Selected Stock Reason</span>
                <strong>{symbol}</strong>
              </div>
              <p>{fullReason(item)}</p>
              <div className="selected-stock-actions">
                <button className="btn-secondary" type="button" onClick={() => handlePrimaryPin(item)}><Pin size={15} /> Pin</button>
                <button className="btn-secondary" type="button" onClick={() => addToDashboardMonitor(item)}><BellPlus size={15} /> Monitor</button>
                <button className="btn-secondary" type="button" onClick={() => pushSymbolToScanner('intraday', symbol)}><ArrowRightLeft size={15} /> Intraday</button>
                <button className="btn-secondary" type="button" onClick={() => pushSymbolToScanner('swing', symbol)}><Star size={15} /> Swing</button>
                <button className="btn-secondary" type="button" onClick={() => addToCompare(symbol)}><GitCompare size={15} /> Compare</button>
                <button className="btn-secondary" type="button" onClick={() => openChart(symbol)}><Telescope size={15} /> Chart</button>
                <button className="btn-secondary" type="button" onClick={() => exportSingleRow(item)}><FileDown size={15} /> CSV</button>
                <button className="icon-button" type="button" title="Close details" onClick={() => setSelectedStock(null)}>x</button>
              </div>
            </div>
          )}
          </React.Fragment>
        );
      })}
      </div>
      </div>
      {sortedItems.length > effectivePageSize && (
        <div className="pagination-bar">
          <span>{sortedItems.length} stocks sorted by {String(sortKey)} {sortDirection}</span>
          <div>
            <button className="icon-button" type="button" title="Previous page" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}><ArrowLeft size={15} /></button>
            <strong>Page {page} / {pageCount}</strong>
            <button className="icon-button" type="button" title="Next page" disabled={page >= pageCount} onClick={() => setPage((value) => Math.min(pageCount, value + 1))}><ArrowRight size={15} /></button>
          </div>
        </div>
      )}
    </div>
  );
}

export const StockGrid = memo(StockGridComponent);
export default StockGrid;
