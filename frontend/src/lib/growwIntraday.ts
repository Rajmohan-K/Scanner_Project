import { getGrowwIntradayStocks, getScanStatus, normalizeStockRow, startScan } from '@/lib/api';
import { addStocksToLiveMonitor } from '@/lib/liveMonitor';

export const GROWW_RESULTS_KEY = 'groww-intraday-results';
export const GROWW_SETTINGS_KEY = 'groww-intraday-auto-settings';
export const GROWW_EVENT = 'groww-intraday-results-updated';

export type GrowwAutoSettings = {
  enabled: boolean;
  intervalMinutes: number;
  limit: number;
};

export type GrowwSavedResults = {
  rows: any[];
  symbols: string[];
  scanId: string;
  updatedAt: string;
  sourceCount: number;
  resolvedCount: number;
  message: string;
};

export const defaultGrowwSettings: GrowwAutoSettings = {
  enabled: false,
  intervalMinutes: 15,
  limit: 80,
};

export function readGrowwSettings(): GrowwAutoSettings {
  if (typeof window === 'undefined') return defaultGrowwSettings;
  try {
    return { ...defaultGrowwSettings, ...JSON.parse(window.localStorage.getItem(GROWW_SETTINGS_KEY) || '{}') };
  } catch {
    return defaultGrowwSettings;
  }
}

export function writeGrowwSettings(settings: Partial<GrowwAutoSettings>) {
  if (typeof window === 'undefined') return;
  const next = { ...readGrowwSettings(), ...settings };
  next.intervalMinutes = Math.max(1, Math.min(240, Number(next.intervalMinutes || defaultGrowwSettings.intervalMinutes)));
  next.limit = Math.max(5, Math.min(200, Number(next.limit || defaultGrowwSettings.limit)));
  window.localStorage.setItem(GROWW_SETTINGS_KEY, JSON.stringify(next));
  window.dispatchEvent(new CustomEvent(GROWW_EVENT, { detail: { settings: next } }));
}

export function readGrowwResults(): GrowwSavedResults {
  if (typeof window === 'undefined') {
    return { rows: [], symbols: [], scanId: '', updatedAt: '', sourceCount: 0, resolvedCount: 0, message: '' };
  }
  try {
    const payload = JSON.parse(window.localStorage.getItem(GROWW_RESULTS_KEY) || '{}');
    return {
      rows: Array.isArray(payload.rows) ? payload.rows : [],
      symbols: Array.isArray(payload.symbols) ? payload.symbols : [],
      scanId: payload.scanId || '',
      updatedAt: payload.updatedAt || '',
      sourceCount: Number(payload.sourceCount || 0),
      resolvedCount: Number(payload.resolvedCount || 0),
      message: payload.message || '',
    };
  } catch {
    return { rows: [], symbols: [], scanId: '', updatedAt: '', sourceCount: 0, resolvedCount: 0, message: '' };
  }
}

export function writeGrowwResults(payload: GrowwSavedResults) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(GROWW_RESULTS_KEY, JSON.stringify(payload));
  window.dispatchEvent(new CustomEvent(GROWW_EVENT, { detail: { results: payload } }));
}

export function pushSymbolsToIntraday(symbols: string[]) {
  if (typeof window === 'undefined') return;
  const next = Array.from(new Set(symbols.map((symbol) => String(symbol).toUpperCase()).filter(Boolean)));
  window.localStorage.setItem('custom-intraday-symbols', next.join(', '));
  window.dispatchEvent(new CustomEvent('custom-scanner-symbols', { detail: { target: 'intraday', symbols: next } }));
}

async function waitForCompletion(scanId: string, timeoutMs = 240000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const status = await getScanStatus(scanId);
    if (status?.status === 'completed') return status.result || status;
    if (['error', 'cancelled'].includes(String(status?.status))) {
      throw new Error(status?.message || status?.result?.message || `Scan ${status.status}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  throw new Error('Groww intraday scan timed out');
}

export async function runGrowwIntradayAnalysis(limit = 80) {
  const source = await getGrowwIntradayStocks(limit);
  const symbols: string[] = Array.from(
    new Set<string>((source.symbols || []).map((symbol: string) => String(symbol).toUpperCase()).filter(Boolean))
  );
  if (!symbols.length) {
    throw new Error('Groww source returned no resolved .NS symbols');
  }

  pushSymbolsToIntraday(symbols);
  const started = await startScan({
    symbols,
    scan_mode: 'groww-intraday',
    period: '30d',
    interval: '5m',
    candidate_pool: Math.max(symbols.length, 25),
    validation_pool: 0,
    top_n: 20,
    workers: Math.min(4, Math.max(1, symbols.length)),
    strict_shortlist: false,
    min_expected_return_pct: 0,
    min_ml_probability: 0,
    min_risk_reward: 0,
    min_data_reliability_score: 0,
    market_open_analysis: true,
    telegram_category: 'Intraday',
  });

  const completed = await waitForCompletion(started.scan_id);
  const output = completed.result || completed;
  const rows = (output.final_top_10 || output.ranked || output.top_25 || output.filtered_150 || output.results || [])
    .map(normalizeStockRow);
  addStocksToLiveMonitor(rows.slice(0, 20), 'groww-intraday');
  pushSymbolsToIntraday(rows.map((row: any) => row.symbol || row.stock).filter(Boolean));

  const saved: GrowwSavedResults = {
    rows,
    symbols,
    scanId: started.scan_id,
    updatedAt: new Date().toISOString(),
    sourceCount: Number(source.count || 0),
    resolvedCount: symbols.length,
    message: `Groww intraday analysis completed with ${rows.length} filtered stocks.`,
  };
  writeGrowwResults(saved);
  return saved;
}
