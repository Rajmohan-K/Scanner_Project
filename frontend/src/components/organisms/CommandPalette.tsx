"use client";
import React, { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { BarChart3, Building2, FileText, Gauge, LineChart, Loader2, Radar, Search, Settings, Star, Target, Trophy, X } from 'lucide-react';
import { searchStocks, type StockSearchResult } from '@/lib/api';

const commands = [
  { label: 'Open Dashboard', hint: 'Executive summary and opportunities', href: '/dashboard', icon: Gauge },
  { label: 'Run Scanner V20', hint: 'Profitability gate and scan controls', href: '/scan-center', icon: Radar },
  { label: 'Priority Picks', hint: 'Top intraday and swing picks with target/stop report', href: '/priority-picks', icon: Trophy },
  { label: 'Watchlist Monitor', hint: 'Live watchlist monitoring, breakout alerts, and alert rules', href: '/watchlist', icon: Star },
  { label: 'Premarket Pipeline', hint: 'Premarket discovery and 9:08 open confirmation', href: '/premarket', icon: Target },
  { label: 'Intraday Workbench', hint: 'Short-term setups and live monitor', href: '/intraday', icon: BarChart3 },
  { label: 'Swing Intelligence', hint: 'Multi-day opportunity analysis', href: '/swing', icon: LineChart },
  { label: 'Reports Library', hint: 'Saved scans and exports', href: '/reports', icon: FileText },
  { label: 'Personalization', hint: 'Themes, settings, modules', href: '/settings', icon: Settings },
];

export default function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [stockResults, setStockResults] = useState<StockSearchResult[]>([]);
  const [stockLoading, setStockLoading] = useState(false);
  const [stockError, setStockError] = useState('');

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setOpen((value) => !value);
      }
      if (event.key === 'Escape') setOpen(false);
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  useEffect(() => {
    const needle = query.trim();
    if (!open || needle.length < 2) {
      setStockResults([]);
      setStockError('');
      setStockLoading(false);
      return;
    }
    let cancelled = false;
    setStockLoading(true);
    const timeout = window.setTimeout(() => {
      searchStocks(needle, 8)
        .then((payload) => {
          if (!cancelled) {
            setStockResults(payload.results || []);
            setStockError('');
          }
        })
        .catch((error) => {
          if (!cancelled) {
            setStockResults([]);
            setStockError(error?.message || 'Stock search unavailable');
          }
        })
        .finally(() => {
          if (!cancelled) setStockLoading(false);
        });
    }, 220);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [open, query]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return commands;
    return commands.filter((command) => `${command.label} ${command.hint}`.toLowerCase().includes(needle));
  }, [query]);

  function runCommand(href: string) {
    setOpen(false);
    setQuery('');
    router.push(href);
  }

  function openStock(symbol: string) {
    setOpen(false);
    setQuery('');
    router.push(`/stocks/${encodeURIComponent(symbol)}`);
  }

  return (
    <>
      <button className="command-trigger" type="button" onClick={() => setOpen(true)}>
        <Search size={16} />
        <span>Search or command</span>
        <kbd>Ctrl K</kbd>
      </button>
      {open && (
        <div className="command-backdrop" role="presentation" onClick={() => setOpen(false)}>
          <section className="command-palette" role="dialog" aria-modal="true" aria-label="Command palette" onClick={(event) => event.stopPropagation()}>
            <header>
              <Search size={18} />
              <input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search stocks, screens, reports, workflows..." />
              <button className="icon-button" type="button" title="Close command palette" onClick={() => setOpen(false)}><X size={16} /></button>
            </header>
            <div className="command-list">
              {(stockLoading || stockResults.length > 0 || stockError) && (
                <div className="command-section-label">
                  <span>Stocks</span>
                  {stockLoading && <Loader2 size={14} className="spin" />}
                </div>
              )}
              {stockResults.map((stock) => (
                <button className="stock-search-result" key={stock.symbol} type="button" onClick={() => openStock(stock.symbol)}>
                  <Building2 size={18} />
                  <span><strong>{stock.symbol}</strong><small>{stock.name} · {stock.exchange}</small></span>
                  <Star size={14} />
                </button>
              ))}
              {stockError && <div className="command-empty">{stockError}</div>}
              {filtered.length > 0 && <div className="command-section-label"><span>Workflows</span></div>}
              {filtered.map(({ label, hint, href, icon: Icon }) => (
                <button key={href} type="button" onClick={() => runCommand(href)}>
                  <Icon size={18} />
                  <span><strong>{label}</strong><small>{hint}</small></span>
                  <Star size={14} />
                </button>
              ))}
              {!filtered.length && !stockResults.length && !stockLoading && !stockError && <div className="command-empty">No matching stock or workflow found</div>}
            </div>
          </section>
        </div>
      )}
    </>
  );
}
