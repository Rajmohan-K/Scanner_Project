export type LiveMonitorInput = {
  symbol?: string;
  stock?: string;
  live_price?: number;
  current_price?: number;
  last_close?: number;
  entry_price?: number;
  entry?: number;
  stop_loss?: number;
  stoploss?: number;
  target1?: number;
  target_1?: number;
  target2?: number;
  target_2?: number;
  telegram?: boolean;
  source?: string;
};

export type LiveMonitorRow = {
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
  source?: string;
};

const MONITOR_KEY = 'dashboard-live-monitor';
export const LIVE_MONITOR_EVENT = 'dashboard-live-monitor-updated';

export function normalizeMonitorSymbol(value: string) {
  const cleaned = value.trim().replace(/\s+/g, '').toUpperCase();
  if (!cleaned) return '';
  return cleaned.includes('.') ? cleaned : `${cleaned}.NS`;
}

function numberOrUndefined(value: unknown) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? Math.round(numeric * 100) / 100 : undefined;
}

export function rowFromStock(stock: LiveMonitorInput, source = 'scan'): LiveMonitorRow | null {
  const symbol = normalizeMonitorSymbol(String(stock.symbol || stock.stock || ''));
  if (!symbol) return null;
  return {
    symbol,
    live_price: numberOrUndefined(stock.live_price ?? stock.current_price ?? stock.last_close),
    entry_price: numberOrUndefined(stock.entry_price ?? stock.entry),
    stop_loss: numberOrUndefined(stock.stop_loss ?? stock.stoploss),
    target1: numberOrUndefined(stock.target1 ?? stock.target_1),
    target2: numberOrUndefined(stock.target2 ?? stock.target_2),
    telegram: stock.telegram ?? false,
    last_updated: new Date().toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true }),
    source,
  };
}

export function readLiveMonitorRows(): LiveMonitorRow[] {
  if (typeof window === 'undefined') return [];
  try {
    const rows = JSON.parse(window.localStorage.getItem(MONITOR_KEY) || '[]');
    return Array.isArray(rows) ? rows : [];
  } catch {
    return [];
  }
}

export function writeLiveMonitorRows(rows: LiveMonitorRow[]) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(MONITOR_KEY, JSON.stringify(rows));
  window.dispatchEvent(new CustomEvent(LIVE_MONITOR_EVENT, { detail: { rows } }));
}

export function addStocksToLiveMonitor(stocks: LiveMonitorInput[], source = 'scan') {
  const additions = stocks.map((stock) => rowFromStock(stock, source)).filter(Boolean) as LiveMonitorRow[];
  if (typeof window === 'undefined' || !additions.length) return { added: 0, updated: 0, rows: [] as LiveMonitorRow[] };
  const current = readLiveMonitorRows();
  const bySymbol = new Map(current.map((row) => [row.symbol, row]));
  let added = 0;
  let updated = 0;
  additions.forEach((row) => {
    const existing = bySymbol.get(row.symbol);
    if (existing) {
      bySymbol.set(row.symbol, {
        ...existing,
        ...row,
        live_price: row.live_price ?? existing.live_price,
        entry_price: row.entry_price ?? existing.entry_price,
        stop_loss: row.stop_loss ?? existing.stop_loss,
        target1: row.target1 ?? existing.target1,
        target2: row.target2 ?? existing.target2,
        telegram: existing.telegram ?? row.telegram,
        telegram_status: '',
      });
      updated += 1;
    } else {
      bySymbol.set(row.symbol, row);
      added += 1;
    }
  });
  const rows = Array.from(bySymbol.values()).sort((a, b) => additions.some((row) => row.symbol === b.symbol) ? 1 : additions.some((row) => row.symbol === a.symbol) ? -1 : 0);
  writeLiveMonitorRows(rows);
  return { added, updated, rows };
}
