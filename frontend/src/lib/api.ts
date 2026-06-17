import axios from 'axios';

export type ApiTargetMode = 'local' | 'server';

const API_TARGET_KEY = 'scanner-api-target';
const LOCAL_API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:5000';
const SERVER_API_BASE = 'http://16.176.23.42:5000';

function browserStorage() {
  return typeof window !== 'undefined' ? window.localStorage : null;
}

export function getApiTargetMode(): ApiTargetMode {
  const stored = browserStorage()?.getItem(API_TARGET_KEY);
  return stored === 'server' ? 'server' : 'local';
}

export function getApiBaseUrl(mode: ApiTargetMode = getApiTargetMode()) {
  return mode === 'server' ? SERVER_API_BASE : LOCAL_API_BASE;
}

export function setApiTargetMode(mode: ApiTargetMode) {
  browserStorage()?.setItem(API_TARGET_KEY, mode);
  clearApiCache();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('scanner-api-target-changed', { detail: { mode, baseUrl: getApiBaseUrl(mode) } }));
  }
}

const client = axios.create({
  baseURL: getApiBaseUrl(),
  headers: { 'Content-Type': 'application/json' },
  timeout: 15000,
});

client.interceptors.request.use((config) => {
  config.baseURL = getApiBaseUrl();
  return config;
});

const getCache = new Map<string, { expiresAt: number; data: any }>();

async function cachedGet<T = any>(url: string, ttlMs = 15000): Promise<T> {
  const key = url;
  const cached = getCache.get(key);
  const now = Date.now();
  if (cached && cached.expiresAt > now) return cached.data as T;
  const response = await client.get(url);
  getCache.set(key, { expiresAt: now + ttlMs, data: response.data });
  return response.data as T;
}

export function clearApiCache() {
  getCache.clear();
}

async function liveGet<T = any>(url: string): Promise<T> {
  const separator = url.includes('?') ? '&' : '?';
  const response = await client.get(`${url}${separator}_ts=${Date.now()}`);
  return response.data as T;
}

export type ScanPayload = {
  symbols?: string[] | string;
  period?: string;
  interval?: string;
  benchmark?: string;
  top_n?: number;
  workers?: number;
  candidate_pool?: number;
  validation_pool?: number;
  strict_shortlist?: boolean;
  min_expected_return_pct?: number;
  min_ml_probability?: number;
  min_risk_reward?: number;
  max_stop_distance_pct?: number;
  min_data_reliability_score?: number;
  min_profitability_score?: number;
  auto_nse_universe?: boolean;
  refresh_universe?: boolean;
  universe_output?: string;
  symbols_file?: string;
  scan_mode?: string;
  market_open_analysis?: boolean;
  market_open_time?: string;
  market_open_interval?: string;
  notify_telegram?: boolean;
  telegram_category?: string;
  type?: string;
  options?: Record<string, unknown>;
};

export function normalizeStockRow(row: any) {
  return {
    ...row,
    symbol: row.symbol || row.stock,
    stock: row.stock || row.symbol,
    live_price: row.live_price ?? row.current_price ?? row.currentPrice ?? row.last_close,
    entry_price: row.entry_price ?? row.entry ?? row.entryPrice,
    stop_loss: row.stop_loss ?? row.stoploss ?? row.stopLoss,
    target1: row.target1 ?? row.target_1,
    target2: row.target2 ?? row.target_2,
    target3: row.target3 ?? row.target_3,
    rrr: row.rrr ?? row.risk_reward ?? row.risk_reward_ratio ?? row.riskRewardRatio,
    expected_return: row.expected_return ?? row.expectedReturn,
    stop_distance_pct: row.stop_distance_pct ?? row.stopDistancePct,
    ml_score: row.ml_score ?? row.ml_probability ?? row.mlScore,
    market_cap: row.market_cap ?? row.marketCap,
    pe: row.pe ?? row.pe_ratio ?? row.peRatio,
    roe: row.roe,
    eps_growth: row.eps_growth ?? row.epsGrowth,
    technical_score: row.technical_score ?? row.technicalScore ?? row.score,
    profitability_score: row.profitability_score ?? row.profitabilityScore ?? row.final_ai_score,
    quality_score: row.quality_score ?? row.qualityScore,
    fundamental_score: row.fundamental_score ?? row.fundamentalScore,
    confidence_pct: row.confidence_pct ?? row.confidence ?? row.overall_confidence,
    data_reliability_score: row.data_reliability_score ?? row.dataReliabilityScore,
    volume_strength: row.volume_strength ?? row.volumeStrength,
    breakout_strength: row.breakout_strength ?? row.breakoutStrength,
    pattern: row.pattern ?? row.pattern_detected ?? row.patternDetected,
    trend: row.trend ?? row.trend_direction ?? row.trendDirection,
    action: row.action ?? row.ai_rating ?? row.recommendation ?? row.premarket_action ?? row.signal ?? row.trade_type,
    reason: row.reason ?? row.reasoning ?? row.explanation ?? row.recommendation_reason ?? row.trade_reason ?? row.premarket_reasons ?? row.message,
    quality_filter_passed: row.quality_filter_passed ?? row.qualityFilterPassed,
    quality_filter_reasons: row.quality_filter_reasons ?? row.qualityFilterReasons,
    generated_at: row.generated_at ?? row.created_at,
    last_updated: row.last_updated ?? row.updated_at,
    tag: row.tag ?? String(row.best_horizon || '').toLowerCase(),
  };
}

export function isActionableStock(row: any) {
  const action = String(row.action || row.recommendation || row.premarket_action || row.signal || row.trade_type || '').toUpperCase();
  if (action.includes('AVOID') || action.includes('HOLD') || action.includes('WATCH')) return false;
  return action.includes('BUY') || action.includes('SELL');
}

type ExtractOptions = {
  actionableOnly?: boolean;
  source?: 'best' | 'filtered';
};

function firstRows(payload: any, options: ExtractOptions = {}) {
  const root = payload?.result || payload || {};
  const sources = options.source === 'filtered'
    ? [root.top_25, root.filtered_150, root.results, root.final_top_10, root.ranked, root.all_stocks_live_data]
    : [root.final_top_10, root.ranked, root.top_25, root.filtered_150, root.results, root.all_stocks_live_data];
  return sources.find((rows) => Array.isArray(rows) && rows.length) || [];
}

export function extractStockRows(payload: any, options: ExtractOptions = {}) {
  const rows = firstRows(payload, options);
  const normalized = Array.isArray(rows) ? rows.map(normalizeStockRow) : [];
  return options.actionableOnly === false ? normalized : normalized.filter(isActionableStock);
}

export async function getLatestScanWithResults(options: ExtractOptions & { scanMode?: string | RegExp } = {}) {
  const list = await listScans();
  const scans = (list?.scans || []).filter((scan: any) => {
    const validId = /^\d{8}_\d{6}$/.test(String(scan.scan_id || scan.id || ''));
    if (!validId) return false;
    if (!options.scanMode) return true;
    const mode = `${scan.scan_mode || scan.scan_type || scan.type || ''}`;
    return typeof options.scanMode === 'string' ? mode.includes(options.scanMode) : options.scanMode.test(mode);
  });
  for (const scan of scans) {
    const scanId = scan.scan_id || scan.id;
    if (!scanId) continue;
    const detail = await getScanDetail(scanId);
    const rows = extractStockRows(detail, options);
    if (rows.length) return { scan: detail, rows, scans };
  }
  return { scan: null, rows: [], scans };
}

export async function getScanSummaries() {
  const list = await listScans();
  return (list?.scans || []).filter((scan: any) => /^\d{8}_\d{6}$/.test(String(scan.scan_id || scan.id || '')));
}

export async function waitForScanResult(scanId: string, timeoutMs = 300000, intervalMs = 2500) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const status = await getScanStatus(scanId);
    if (status?.status === 'completed') {
      return {
        status,
        rows: extractStockRows(status),
      };
    }
    if (status?.status === 'error' || status?.status === 'cancelled') {
      throw new Error(status?.result?.message || status?.message || `Scan ${status.status}`);
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error('Scan timed out before backend returned results');
}

export async function getHealth() {
  return liveGet('/api/health');
}

export async function getMarketWidgets() {
  return liveGet('/api/market/widgets');
}

export async function getActiveScan() {
  const response = await client.get('/api/scan/active');
  return response.data;
}

export async function getActiveScans() {
  const response = await client.get('/api/scan/active/all');
  return response.data;
}

export async function startScan(payload: ScanPayload) {
  const response = await client.post('/api/scan/start', payload);
  clearApiCache();
  return response.data;
}

export async function getGrowwIntradayStocks(limit = 80) {
  return liveGet(`/api/sources/groww/intraday?limit=${limit}`);
}

export async function stopScan(scanId: string) {
  const response = await client.post('/api/scan/stop', { scan_id: scanId });
  clearApiCache();
  return response.data;
}

export async function stopAllScans() {
  const response = await client.post('/api/scan/stop-all');
  clearApiCache();
  return response.data;
}

export async function pauseScan(scanId: string) {
  const response = await client.post('/api/scan/pause', { scan_id: scanId });
  return response.data;
}

export async function resumeScan(scanId: string) {
  const response = await client.post('/api/scan/resume', { scan_id: scanId });
  return response.data;
}

export async function getScanStatus(scanId: string) {
  const response = await client.get(`/api/scan/${scanId}/status`);
  return response.data;
}

export async function listScans() {
  const response = await client.get('/api/scans');
  return response.data;
}

export async function getScanDetail(scanId: string) {
  return cachedGet(`/api/scans/${scanId}`, 20000);
}

export async function getSettings() {
  return cachedGet('/api/settings', 30000);
}

export async function saveSettings(payload: unknown) {
  const response = await client.post('/api/settings', payload);
  clearApiCache();
  return response.data;
}

export async function getWatchlistOrder() {
  return cachedGet('/api/watchlist/order', 30000);
}

export async function saveWatchlistOrder(order: string[]) {
  const response = await client.post('/api/watchlist/order', { order });
  clearApiCache();
  return response.data;
}

export async function getV20Dashboard() {
  return liveGet('/api/v20/dashboard');
}

export async function getV20Indices() {
  return liveGet('/api/v20/indices');
}

export async function getV20Stocks(params: Record<string, string | number | boolean | undefined> = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') query.set(key, String(value));
  });
  return liveGet(`/api/v20/stocks?${query.toString()}`);
}

export async function getV20Quote(symbol: string) {
  return liveGet(`/api/v20/quote/${encodeURIComponent(symbol)}`);
}

export async function getQuickIntradaySignal(symbol: string, interval = '5m') {
  return liveGet(`/api/intraday/quick-signal/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(interval)}`);
}

export async function saveV20Scanner(name: string, config: Record<string, unknown>) {
  const response = await client.post('/api/v20/saved-scanners', { name, config });
  clearApiCache();
  return response.data;
}

export async function saveV20Filter(name: string, filters: Record<string, unknown>) {
  const response = await client.post('/api/v20/saved-filters', { name, filters });
  clearApiCache();
  return response.data;
}

export async function addV20WatchlistItem(symbol: string) {
  const response = await client.post('/api/v20/watchlist', { symbol });
  clearApiCache();
  return response.data;
}

export async function createV20Alert(payload: { symbol?: string; alert_type: string; condition: string; threshold: number }) {
  const response = await client.post('/api/v20/alerts', payload);
  clearApiCache();
  return response.data;
}

export async function createV20PaperTrade(payload: { symbol: string; side: string; quantity: number; entry_price: number }) {
  const response = await client.post('/api/v20/paper-trades', payload);
  clearApiCache();
  return response.data;
}

export async function sendTelegramStockAlert(payload: Record<string, unknown>) {
  try {
    const response = await client.post('/api/telegram/stock-alert', payload);
    return response.data;
  } catch (error: any) {
    throw new Error(error?.response?.data?.message || error?.message || 'Telegram alert failed');
  }
}
