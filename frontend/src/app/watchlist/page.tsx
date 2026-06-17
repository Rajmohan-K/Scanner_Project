"use client";
import React, { useEffect, useMemo, useState } from 'react';
import StockGrid from '@/components/molecules/LazyStockGrid';
import { getLatestScanWithResults, getWatchlistOrder, saveWatchlistOrder } from '@/lib/api';
import { useDispatch } from 'react-redux';
import { setSymbols } from '@/state/watchlistSlice';
import { useToast } from '@/components/layout/ToastProvider';
import { MetricTile, PageHero, TerminalPanel, Toolbar } from '@/components/terminal/TerminalPrimitives';
import { Bell, Pin, ShieldAlert, Star } from 'lucide-react';

export default function WatchlistPage() {
  const dispatch = useDispatch();
  const toast = useToast();
  const [watch, setWatch] = useState<any[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [symbolText, setSymbolText] = useState('');

  function normalizeSymbolToken(value: string) {
    const cleaned = value.trim().replace(/\s+/g, '').toUpperCase();
    if (!cleaned) return '';
    return cleaned.includes('.') ? cleaned : `${cleaned}.NS`;
  }

  function parseSymbols(value: string) {
    return Array.from(new Set(value.split(/[\s,;]+/).map(normalizeSymbolToken).filter(Boolean)));
  }

  function normalizeSymbolText(value: string) {
    return parseSymbols(value).join(', ');
  }

  useEffect(() => {
    async function load() {
      try {
        const s = await getLatestScanWithResults();
        const results = s.rows || [];
        const orderResponse = await getWatchlistOrder();
        const order: string[] = orderResponse?.watchlist_order || [];
        setSymbolText(order.join(', '));
        const ordered = [...results].sort((a, b) => {
          const left = order.indexOf(a.stock || a.symbol);
          const right = order.indexOf(b.stock || b.symbol);
          if (left === -1 && right === -1) return 0;
          if (left === -1) return 1;
          if (right === -1) return -1;
          return left - right;
        });
        setWatch(ordered);
        dispatch(setSymbols(order));
      } catch (err) {
        setWatch([]);
        toast?.push('Unable to load live watchlist data from backend', 'error');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [dispatch, toast]);

  async function handleOrderChange(items: any[]) {
    const symbols = items.map((item) => item.stock || item.symbol).filter(Boolean);
    setWatch(items);
    dispatch(setSymbols(symbols));
    try {
      await saveWatchlistOrder(symbols);
      toast?.push('Watchlist order saved', 'success');
    } catch (err) {
      toast?.push('Unable to persist watchlist order', 'error');
    }
  }

  async function handleSaveSymbols() {
    const symbols = parseSymbols(symbolText);
    if (!symbols.length) {
      toast?.push('Enter at least one watchlist stock', 'warning');
      return;
    }
    const normalized = symbols.join(', ');
    setSymbolText(normalized);
    dispatch(setSymbols(symbols));
    try {
      await saveWatchlistOrder(symbols);
      toast?.push(`Saved ${symbols.length} watchlist symbols`, 'success');
    } catch {
      toast?.push('Unable to save watchlist symbols', 'error');
    }
  }

  const filtered = useMemo(() => watch.filter((item) => `${item.symbol} ${item.stock} ${item.sector}`.toLowerCase().includes(query.toLowerCase())), [watch, query]);
  const breakoutAlerts = filtered.filter((item) => /breakout/i.test(`${item.reason || ''} ${item.pattern || ''}`)).length;
  const highConfidence = filtered.filter((item) => Number(item.confidence_pct || item.confidence || 0) >= 75).length;
  const riskWarnings = filtered.filter((item) => Number(item.risk_score || 0) >= 50 || /high/i.test(String(item.risk_level || ''))).length;

  return (
    <main>
      <PageHero
        eyebrow="Watchlist"
        title="Pinned Symbols and Alert Monitor"
        description="Drag table rows into priority order, track watchlist alerts, and push symbols into dashboard, intraday, or swing workflows."
        metrics={[
          { label: 'Pinned', value: String(filtered.length), tone: 'good' },
          { label: 'Alerts', value: '8', tone: 'warn' },
          { label: 'Synced', value: 'Live', tone: 'good' },
        ]}
      />
      <div className="metric-grid">
        <MetricTile label="Breakout Alerts" value={breakoutAlerts} icon={Bell} tone={breakoutAlerts ? 'good' : 'warn'} />
        <MetricTile label="Pinned Leaders" value={String(filtered.length)} icon={Pin} tone={filtered.length ? 'info' : 'warn'} />
        <MetricTile label="High Confidence" value={highConfidence} icon={Star} tone={highConfidence ? 'good' : 'warn'} />
        <MetricTile label="Risk Warnings" value={riskWarnings} icon={ShieldAlert} tone={riskWarnings ? 'bad' : 'good'} />
      </div>
      <TerminalPanel eyebrow="Watchlist Board" title="Drag to Reorder">
        <div className="symbol-editor">
          <label className="field field--wide">
            <span>Edit Watchlist Stocks</span>
            <textarea
              value={symbolText}
              onBlur={() => setSymbolText(normalizeSymbolText(symbolText))}
              onChange={(event) => setSymbolText(event.target.value)}
              placeholder="Enter stocks separated by comma or space"
              rows={3}
            />
          </label>
          <div className="symbol-editor__actions">
            <button className="btn-primary" type="button" onClick={handleSaveSymbols}>Save Watchlist</button>
            <button className="btn-secondary" type="button" onClick={() => setSymbolText(normalizeSymbolText(symbolText))}>Normalize .NS</button>
            <button className="btn-secondary" type="button" onClick={() => setSymbolText('')}>Clear</button>
            <span>{parseSymbols(symbolText).length ? `${parseSymbols(symbolText).length} symbols ready` : 'No stocks entered'}</span>
          </div>
        </div>
        <Toolbar search={query} setSearch={setQuery} tabs={['All', 'Alerts', 'Pinned', 'High Confidence']} activeTab="All" onTabChange={() => {}} />
        <StockGrid items={filtered} loading={loading} onReorder={handleOrderChange} />
      </TerminalPanel>
    </main>
  );
}
