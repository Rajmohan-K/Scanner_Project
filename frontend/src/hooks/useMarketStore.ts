import { create } from 'zustand';

export type TickPayload = {
  type?: string;
  symbol?: string;
  price?: number;
  current_price?: number;
  change?: number;
  change_pct?: number;
  change_percent?: number;
  volume?: number;
  timestamp?: string;
  updated_at?: string;
  analysis?: Record<string, unknown>;
  quote?: Record<string, unknown>;
  [key: string]: unknown;
};

export type ConnectionStatus = 'Connected' | 'Reconnecting' | 'Stale Data' | 'Backend Down' | 'Connecting';

interface MarketStore {
  quotes: Record<string, TickPayload>;
  searchSuggestions: any[];
  activeFilters: Record<string, unknown>;
  alerts: any[];
  connectionStatus: ConnectionStatus;
  lastUpdated: string | null;
  updateTick: (symbol: string, tick: TickPayload) => void;
  applySnapshot: (snapshot: Record<string, any>) => void;
  setInitialQuotes: (initial: Record<string, TickPayload>) => void;
  setConnectionStatus: (status: ConnectionStatus) => void;
  setLastUpdated: (ts: string) => void;
  setSearchSuggestions: (suggestions: any[]) => void;
  setActiveFilters: (filters: Record<string, unknown>) => void;
  setAlerts: (alerts: any[]) => void;
}

function aliasKeys(symbol: string, tick: TickPayload = {}) {
  const values = [
    symbol,
    tick.symbol,
    tick.isin,
    tick.nse_symbol,
    tick.bse_symbol,
    tick.nse_ticker,
    tick.bse_ticker,
  ];
  const keys = new Set<string>();
  values.forEach((value) => {
    const raw = String(value || '').trim().toUpperCase();
    if (!raw) return;
    keys.add(raw);
    if (raw.endsWith('.NS') || raw.endsWith('.BO')) keys.add(raw.slice(0, -3));
  });
  const base = String(symbol || '').trim().toUpperCase();
  if (base && !base.includes('.') && !base.startsWith('IN')) keys.add(`${base}.NS`);
  return Array.from(keys);
}

export const useMarketStore = create<MarketStore>((set) => ({
  quotes: {},
  searchSuggestions: [],
  activeFilters: {},
  alerts: [],
  connectionStatus: 'Connecting',
  lastUpdated: null,
  updateTick: (symbol, tick) =>
    set((state) => {
      const keys = aliasKeys(symbol, tick);
      const next = { ...state.quotes };
      const primary = keys[0] || symbol;
      const merged = {
        ...(state.quotes[primary] || {}),
        ...tick,
        symbol: primary,
        price: tick.price ?? tick.current_price ?? state.quotes[primary]?.price,
        change_pct: tick.change_pct ?? tick.change_percent ?? state.quotes[primary]?.change_pct,
        timestamp: tick.timestamp || tick.updated_at || state.quotes[primary]?.timestamp,
      };
      keys.forEach((key) => {
        next[key] = { ...(next[key] || {}), ...merged, symbol: key };
      });
      return {
        quotes: next,
        lastUpdated: tick.timestamp || tick.updated_at || new Date().toISOString(),
      };
    }),
  applySnapshot: (snapshot) =>
    set((state) => {
      const next = { ...state.quotes };
      Object.entries(snapshot || {}).forEach(([symbol, value]) => {
        const tick = value as TickPayload;
        const keys = aliasKeys(symbol, tick);
        const primary = keys[0] || symbol;
        const merged = {
          ...(next[primary] || {}),
          ...tick,
          symbol: primary,
          price: tick.price ?? tick.current_price ?? next[primary]?.price,
          change_pct: tick.change_pct ?? tick.change_percent ?? next[primary]?.change_pct,
          timestamp: tick.timestamp || tick.updated_at || next[primary]?.timestamp,
        };
        keys.forEach((key) => {
          next[key] = { ...(next[key] || {}), ...merged, symbol: key };
        });
      });
      return { quotes: next, lastUpdated: new Date().toISOString() };
    }),
  setInitialQuotes: (initial) =>
    set(() => ({
      quotes: initial,
    })),
  setConnectionStatus: (status) => set(() => ({ connectionStatus: status })),
  setLastUpdated: (ts) => set(() => ({ lastUpdated: ts })),
  setSearchSuggestions: (suggestions) => set(() => ({ searchSuggestions: suggestions })),
  setActiveFilters: (filters) => set(() => ({ activeFilters: filters })),
  setAlerts: (alerts) => set(() => ({ alerts })),
}));

export const useLiveStockStore = useMarketStore;
