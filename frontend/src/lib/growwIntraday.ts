import { analyzeGrowwIntradayStocks, normalizeStockRow } from '@/lib/api';
import { buildPriorityRows, priorityProfitPct } from '@/lib/priorityPicks';
import { hydrateRowsWithUnifiedAnalysis } from '@/lib/unifiedAnalysis';

export const GROWW_RESULTS_KEY = 'groww-intraday-results';
export const GROWW_SETTINGS_KEY = 'groww-intraday-auto-settings';
export const GROWW_EVENT = 'groww-intraday-results-updated';

export type GrowwAutoSettings = {
  enabled: boolean;
  intervalMinutes: number;
  limit: number;
  priorityLimit?: number;
  priorityMinProfitPct?: number;
};

export type GrowwSavedResults = {
  rows: any[];
  symbols: string[];
  scanId: string;
  updatedAt: string;
  sourceCount: number;
  resolvedCount: number;
  analyzedCount?: number;
  cachedCount?: number;
  failedCount?: number;
  priorityRows?: any[];
  message: string;
};

export const defaultGrowwSettings: GrowwAutoSettings = {
  enabled: false,
  intervalMinutes: 15,
  limit: 80,
  priorityLimit: 5,
  priorityMinProfitPct: 3,
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
  next.priorityLimit = Math.max(3, Math.min(5, Number(next.priorityLimit || defaultGrowwSettings.priorityLimit)));
  next.priorityMinProfitPct = Math.max(3, Math.min(5, Number(next.priorityMinProfitPct || defaultGrowwSettings.priorityMinProfitPct)));
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
      analyzedCount: Number(payload.analyzedCount || 0),
      cachedCount: Number(payload.cachedCount || 0),
      failedCount: Number(payload.failedCount || 0),
      priorityRows: buildGrowwPriorityRows(payload.rows || []),
      message: payload.message || '',
    };
  } catch {
    return { rows: [], symbols: [], scanId: '', updatedAt: '', sourceCount: 0, resolvedCount: 0, message: '' };
  }
}

export function writeGrowwResults(payload: GrowwSavedResults) {
  if (typeof window === 'undefined') return;
  const next = { ...payload, priorityRows: payload.priorityRows || buildGrowwPriorityRows(payload.rows || []) };
  window.localStorage.setItem(GROWW_RESULTS_KEY, JSON.stringify(next));
  window.dispatchEvent(new CustomEvent(GROWW_EVENT, { detail: { results: next } }));
}

export function pushSymbolsToIntraday(symbols: string[]) {
  if (typeof window === 'undefined') return;
  const next = Array.from(new Set(symbols.map((symbol) => String(symbol).toUpperCase()).filter(Boolean)));
  window.localStorage.setItem('custom-intraday-symbols', next.join(', '));
  window.dispatchEvent(new CustomEvent('custom-scanner-symbols', { detail: { target: 'intraday', symbols: next } }));
}

export function growwSymbolsText(limit = 80) {
  const latest = readGrowwResults();
  return Array.from(new Set((latest.symbols || latest.rows.map(rowSymbol)).filter(Boolean)))
    .slice(0, limit)
    .join(', ');
}

function rowSymbol(row: any) {
  return String(row?.symbol || row?.stock || '').toUpperCase();
}

export function growwPriorityProfitPct(row: any) {
  return priorityProfitPct(row);
}

function suggestedIntradayTime(row: any) {
  return row?.suggested_time || row?.entry_window || row?.trade_window || 'After VWAP/volume confirmation; avoid fresh entry near close';
}

export function buildGrowwPriorityRows(rows: any[], settings: GrowwAutoSettings = readGrowwSettings()) {
  const minProfit = Number(settings.priorityMinProfitPct || defaultGrowwSettings.priorityMinProfitPct || 3);
  const limit = Number(settings.priorityLimit || defaultGrowwSettings.priorityLimit || 5);
  return buildPriorityRows(rows, {
    horizon: 'intraday',
    includeUnknown: true,
    limit,
    minProfitPct: minProfit,
    sourceName: 'Groww Intraday',
  }).map((row) => ({
    ...row,
    source: row.source || 'groww',
    source_name: row.source_name || 'Groww Intraday',
    suggested_time: suggestedIntradayTime(row),
    priority_reason: row.detailed_priority_reason || row.priority_reason || `Groww priority: ${Number(row.priority_profit_pct || 0).toFixed(2)}% expected profit, RR ${row.risk_reward || '-'}, complete entry/SL/target plan`,
    detailed_priority_reason: row.detailed_priority_reason || row.priority_reason,
  }));
}

export function readGrowwPriorityRows() {
  const latest = readGrowwResults();
  return latest.priorityRows?.length ? latest.priorityRows : buildGrowwPriorityRows(latest.rows || []);
}

function mergeRows(previousRows: any[], nextRows: any[]) {
  const bySymbol = new Map<string, any>();
  previousRows.forEach((row) => {
    const symbol = rowSymbol(row);
    if (symbol) bySymbol.set(symbol, row);
  });
  nextRows.forEach((row) => {
    const symbol = rowSymbol(row);
    if (symbol) bySymbol.set(symbol, { ...bySymbol.get(symbol), ...row });
  });
  return Array.from(bySymbol.values())
    .sort((a, b) => Number(b.intraday_score || b.score || b.profitability_score || 0) - Number(a.intraday_score || a.score || a.profitability_score || 0))
    .slice(0, 120);
}

export const GROWW_PRIORITY_ACTIVE_KEY = 'groww-priority-active-v1';
export const GROWW_PRIORITY_HISTORY_KEY = 'groww-priority-history-v1';
export const GROWW_PRIORITY_UPDATED_EVENT = 'groww-priority-updated';

export type TrackedGrowwPriorityRow = any & {
  key: string;
  status: 'active';
  found_at: string;
  suggested_entry_time: string;
  last_price?: number;
  last_checked?: string;
  lifecycle_reason?: string;
};

export function readGrowwPriorityActive(): TrackedGrowwPriorityRow[] {
  if (typeof window === 'undefined') return [];
  try {
    return JSON.parse(window.localStorage.getItem(GROWW_PRIORITY_ACTIVE_KEY) || '[]');
  } catch {
    return [];
  }
}

export function writeGrowwPriorityActive(rows: TrackedGrowwPriorityRow[]) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(GROWW_PRIORITY_ACTIVE_KEY, JSON.stringify(rows));
  window.dispatchEvent(new Event(GROWW_PRIORITY_UPDATED_EVENT));
}

export function readGrowwPriorityHistory(): any[] {
  if (typeof window === 'undefined') return [];
  try {
    return JSON.parse(window.localStorage.getItem(GROWW_PRIORITY_HISTORY_KEY) || '[]');
  } catch {
    return [];
  }
}

export function writeGrowwPriorityHistory(rows: any[]) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(GROWW_PRIORITY_HISTORY_KEY, JSON.stringify(rows));
  window.dispatchEvent(new Event(GROWW_PRIORITY_UPDATED_EVENT));
}

export function upsertGrowwPriorityRows(newRows: any[]) {
  const active = readGrowwPriorityActive();
  const history = readGrowwPriorityHistory();
  const now = Date.now();
  const recentClosed = new Map(
    history
      .filter((row: any) => now - new Date(row.closed_at).getTime() < 30 * 60 * 1000)
      .map((row: any) => [row.symbol, row])
  );
  const bySymbol = new Map(active.map((row: any) => [row.symbol, row]));
  let added = 0;
  newRows.forEach((row) => {
    const symbol = rowSymbol(row);
    if (!symbol || recentClosed.has(symbol)) return;
    const existing = bySymbol.get(symbol);
    if (existing) {
      bySymbol.set(symbol, {
        ...existing,
        ...row,
        found_at: existing.found_at,
        suggested_entry_time: existing.suggested_entry_time || row.suggested_entry_time || new Date().toISOString(),
        status: 'active',
      });
    } else {
      added += 1;
      bySymbol.set(symbol, {
        ...row,
        symbol,
        status: 'active',
        found_at: new Date().toISOString(),
        suggested_entry_time: row.suggested_entry_time || row.suggested_time || row.generated_at || new Date().toISOString(),
      });
    }
  });
  const nextActive = Array.from(bySymbol.values());
  writeGrowwPriorityActive(nextActive);
  return { active: nextActive, added };
}

export async function runGrowwIntradayAnalysis(limit = 80) {
  const output = await analyzeGrowwIntradayStocks(limit, '5m', 90);
  const symbols: string[] = Array.from(new Set<string>((output.symbols || []).map((symbol: string) => String(symbol).toUpperCase()).filter(Boolean)));
  if (!symbols.length) {
    throw new Error('Groww source returned no resolved .NS symbols');
  }

  const rows = await hydrateRowsWithUnifiedAnalysis((output.rows || []).map(normalizeStockRow), 'intraday', 40);
  const previous = readGrowwResults();
  const mergedRows = mergeRows(previous.rows || [], rows);
  const priorityRows = buildGrowwPriorityRows(mergedRows);

  // Upsert priority candidates into continuous background monitoring list
  upsertGrowwPriorityRows(priorityRows);

  const saved: GrowwSavedResults = {
    rows: mergedRows,
    symbols,
    scanId: output.scan_id || previous.scanId || '',
    updatedAt: new Date().toISOString(),
    sourceCount: Number(output.source_count || 0),
    resolvedCount: Number(output.resolved_count || symbols.length),
    analyzedCount: Number((output.analyzed_symbols || []).length || 0),
    cachedCount: Number((output.cached_symbols || []).length || 0),
    failedCount: Number((output.failed || []).length || 0),
    priorityRows,
    message: output.message || `Groww intraday quick analysis returned ${rows.length} current opportunities; ${mergedRows.length} kept in analyzed cache; ${priorityRows.length} priority picks meet profit and trade-plan rules.`,
  };
  writeGrowwResults(saved);
  return saved;
}
