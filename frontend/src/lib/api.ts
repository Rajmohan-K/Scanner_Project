import axios from 'axios';

export type ApiTargetMode = 'local' | 'server';

const API_TARGET_KEY = 'scanner-api-target';
const OPTIMISTIC_ACTIVE_SCANS_KEY = 'scanner-optimistic-active-scans';
export const SCAN_STATUS_EVENT = 'scanner-active-status-changed';
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
  timeout: 45000,
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

function emitScanStatusChanged() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(SCAN_STATUS_EVENT));
  }
}

function writeOptimisticActiveScans(scans: any[]) {
  const storage = browserStorage();
  if (!storage) return;
  const now = Date.now();
  const fresh = scans.filter((scan) => Number(scan.expiresAt || 0) > now);
  storage.setItem(OPTIMISTIC_ACTIVE_SCANS_KEY, JSON.stringify(fresh));
  emitScanStatusChanged();
}

export function getOptimisticActiveScans() {
  const storage = browserStorage();
  if (!storage) return [];
  try {
    const now = Date.now();
    const rows = JSON.parse(storage.getItem(OPTIMISTIC_ACTIVE_SCANS_KEY) || '[]');
    if (!Array.isArray(rows)) return [];
    const fresh = rows.filter((scan) => Number(scan.expiresAt || 0) > now);
    if (fresh.length !== rows.length) storage.setItem(OPTIMISTIC_ACTIVE_SCANS_KEY, JSON.stringify(fresh));
    return fresh;
  } catch {
    return [];
  }
}

function addOptimisticActiveScan(scan: any) {
  const scanId = scan?.scan_id || scan?.id;
  if (!scanId) return;
  const current = getOptimisticActiveScans().filter((row: any) => (row.scan_id || row.id) !== scanId);
  writeOptimisticActiveScans([
    {
      ...scan,
      scan_id: scanId,
      id: scanId,
      status: scan.status || 'running',
      display_name: scan.display_name || scan.scan_type || scan.scan_mode || 'Live Scan',
      created_at: scan.created_at || new Date().toISOString(),
      expiresAt: Date.now() + 15 * 1000,
      optimistic: true,
    },
    ...current,
  ]);
}

function removeOptimisticActiveScan(scanId?: string) {
  if (!scanId) {
    writeOptimisticActiveScans([]);
    return;
  }
  writeOptimisticActiveScans(getOptimisticActiveScans().filter((row: any) => (row.scan_id || row.id) !== scanId));
}

async function liveGet<T = any>(url: string): Promise<T> {
  const separator = url.includes('?') ? '&' : '?';
  const response = await client.get(`${url}${separator}_ts=${Date.now()}`);
  return response.data as T;
}

export type StockSearchResult = {
  symbol: string;
  name: string;
  exchange: string;
};

export type StockQuotePayload = {
  status: string;
  symbol: string;
  exchange?: string;
  name?: string;
  logo?: string;
  stale?: boolean;
  updated_at?: string;
  source?: string;
  message?: string;
  quote?: {
    current_price?: number;
    previous_close?: number;
    change?: number;
    change_pct?: number;
    open?: number;
    high?: number;
    low?: number;
    volume?: number;
    updated_at?: string;
    [key: string]: unknown;
  };
};

export type StockCandle = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type StockCandlesPayload = {
  status: string;
  symbol: string;
  range: string;
  period?: string;
  interval?: string;
  candles: StockCandle[];
  stale?: boolean;
  updated_at?: string;
  message?: string;
};

export type StockTradePlan = {
  horizon: 'intraday' | 'swing' | string;
  signal?: string;
  valid_for?: string;
  entry_price?: number | null;
  entry_trigger?: number | null;
  stop_loss?: number | null;
  target1?: number | null;
  target2?: number | null;
  target3?: number | null;
  risk_reward_ratio?: number | null;
  risk_per_share?: number | null;
  status?: 'trade_ready' | 'watch_for_confirmation' | 'no_trade' | string;
  reason?: string;
};

export type StockAnalysisPayload = {
  status: string;
  symbol: string;
  message?: string;
  generated_at?: string;
  stale?: boolean;
  scan_type?: string;
  masterRecommendation?: 'BUY' | 'WATCH' | 'AVOID' | string;
  overallScore?: number;
  confidence?: number;
  risk?: string;
  intraday?: { recommendation?: string; score?: number; confidence?: number; entry?: number | null; stopLoss?: number | null; targets?: number[]; reasons?: string[]; invalidation?: string; tradePlan?: StockTradePlan };
  swing?: { recommendation?: string; score?: number; confidence?: number; entry?: number | null; stopLoss?: number | null; targets?: number[]; reasons?: string[]; invalidation?: string; tradePlan?: StockTradePlan };
  breakout?: { status?: string; breakoutLevel?: number; distanceToBreakoutPercent?: number; probability?: number; reasons?: string[] };
  bullishReasons?: string[];
  bearishReasons?: string[];
  finalExplanation?: string;
  lastUpdated?: string;
  dataAgeSeconds?: number;
  isStale?: boolean;
  dataSource?: string;
  analysisVersion?: string;
  settingsVersion?: string;
  cache?: { hit?: boolean; calculatedAt?: string; ageSeconds?: number };
  intraday_view?: 'BUY' | 'WATCH' | 'AVOID' | string;
  swing_view?: 'BUY' | 'WATCH' | 'AVOID' | string;
  breakout_status?: string;
  trend?: string;
  support_levels?: number[];
  resistance_levels?: number[];
  intraday_trade_plan?: StockTradePlan;
  swing_trade_plan?: StockTradePlan;
  entry_price?: number | null;
  stop_loss?: number | null;
  target1?: number | null;
  target2?: number | null;
  target3?: number | null;
  risk_reward_ratio?: number | null;
  volume_analysis?: {
    label?: string;
    latest_volume?: number;
    avg_volume?: number;
    relative_volume?: number;
  };
  indicators?: {
    rsi?: number;
    macd?: { macd?: number; signal?: number; histogram?: number };
    ema20?: number;
    ema50?: number;
    ema200?: number;
    vwap?: number;
  };
  gap_status?: { label?: string; gap_pct?: number };
  delivery_strength?: string;
  master_analysis?: {
    overall_score?: number;
    classification?: string;
    confidence_percent?: number;
    confidence_label?: string;
    probability_of_success?: number;
    final_action?: string;
    expected_holding_period?: string;
    component_scores?: Record<string, number>;
    market_context?: Record<string, unknown>;
    relative_strength?: Record<string, unknown>;
    multi_timeframe?: { alignmentScore?: number; timeframes?: Array<Record<string, unknown>> };
    trend_analysis?: Record<string, unknown>;
    breakout_analysis?: Record<string, unknown>;
    volume_analysis?: Record<string, unknown>;
    momentum_analysis?: Record<string, unknown>;
    risk_analysis?: Record<string, unknown>;
    trade_setups?: Record<string, StockTradePlan>;
    ai_explanation?: {
      summary?: string;
      bullishFactors?: string[];
      bearishFactors?: string[];
      tradeRisks?: string[];
      suggestedAction?: string;
      probabilityOfSuccess?: number;
      confidence?: number;
      expectedHoldingPeriod?: string;
    };
  };
  reason?: string;
  quote?: StockQuotePayload['quote'];
  stock?: StockQuotePayload;
};

export async function searchStocks(query: string, limit = 12) {
  return liveGet<{ status: string; query: string; results: StockSearchResult[] }>(`/api/search?q=${encodeURIComponent(query)}&limit=${limit}`);
}

export async function getStockDetail(symbol: string) {
  return liveGet<StockQuotePayload>(`/api/stocks/${encodeURIComponent(symbol)}`);
}

export async function getStockCandles(symbol: string, range = '1D') {
  return liveGet<StockCandlesPayload>(`/api/stocks/${encodeURIComponent(symbol)}/candles?range=${encodeURIComponent(range)}`);
}

export async function getLiveStockAnalysis(symbol: string, scanType = 'all') {
  return liveGet<StockAnalysisPayload>(`/api/stocks/${encodeURIComponent(symbol)}/analysis?scan_type=${encodeURIComponent(scanType)}`);
}

export function getStockStreamUrl(symbol: string) {
  return `${getApiBaseUrl()}/api/stocks/${encodeURIComponent(symbol)}/stream`;
}

export type WatchlistSnapshot = {
  symbol?: string;
  company_name?: string;
  exchange?: string;
  current_price?: number;
  price_change_pct?: number;
  volume_spike?: number;
  trend?: string;
  breakout_level?: number;
  expected_breakout_price?: number;
  distance_to_breakout_pct?: number;
  current_status?: string;
  intraday_signal?: string;
  swing_signal?: string;
  risk?: string;
  confidence?: number;
  last_alert?: string;
  last_alert_price?: number;
  last_checked?: string;
  support?: number;
  resistance?: number;
  trade_readiness?: string;
  action?: string;
  time_rule_status?: string;
  volume_confirmed?: boolean;
  entry?: number;
  stop_loss?: number;
  target1?: number;
  target2?: number;
  target3?: number;
  gtt_plan?: {
    entry?: number;
    stop_loss?: number;
    target1?: number;
    target2?: number;
    target3?: number;
    quantity_placeholder?: string;
    risk_amount_placeholder?: string;
    note?: string;
  } | null;
  profit_booking_status?: string;
  manual_confirmation_required?: boolean;
  auto_trade_enabled?: boolean;
  trade_reason?: string;
  risk_percent?: number;
  reason?: string;
  stale?: boolean;
};

export type WatchlistItem = {
  symbol: string;
  company_name?: string;
  exchange?: string;
  monitoring_enabled?: boolean;
  alerts_enabled?: boolean;
  telegram_enabled?: boolean;
  desktop_enabled?: boolean;
  sound_enabled?: boolean;
  notes?: string;
  settings?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
  last_checked?: string;
  last_alert?: string;
  snapshot?: WatchlistSnapshot;
};

export type AlertSettings = {
  desktop_enabled?: boolean;
  sound_enabled?: boolean;
  sound_type?: string;
  sound_volume?: number;
  telegram_enabled?: boolean;
  telegram_bot_token?: string;
  telegram_chat_id?: string;
  breakout_distance_pct?: number;
  breakout_volume_multiplier?: number;
  consecutive_candle_count?: number;
  price_move_pct_threshold?: number;
  cooldown_seconds?: number;
  intraday_monitoring?: boolean;
  swing_monitoring?: boolean;
  monitoring_interval_seconds?: number;
  market_hours_only?: boolean;
  severity_filter?: string;
  watchlist_monitoring_enabled?: boolean;
  no_breakout_first_30_minutes?: boolean;
  first_30_minutes_wait_until?: string;
  wait_until_11am_confirmation?: boolean;
  confirmation_wait_until?: string;
  stop_loss_min_pct?: number;
  stop_loss_max_pct?: number;
  default_stop_loss_pct?: number;
  profit_booking_start_pct?: number;
  profit_booking_end_pct?: number;
  book_partial_quantity_pct?: number;
  half_percent_move_threshold?: number;
  gtt_plan_enabled?: boolean;
  future_auto_trade_enabled?: boolean;
};

export type AlertHistoryRecord = {
  alert_id: string;
  symbol: string;
  alert_type: string;
  action?: string;
  severity: string;
  trigger_price?: number;
  last_alert_price?: number;
  percentage_move?: number;
  volume_ratio?: number;
  entry?: number;
  stop_loss?: number;
  target1?: number;
  target2?: number;
  target3?: number;
  volume_confirmation?: boolean;
  time_rule_status?: string;
  risk?: string;
  gtt_plan?: WatchlistSnapshot['gtt_plan'];
  breakout_level?: number;
  message?: string;
  reason?: string;
  confidence?: number;
  created_at?: string;
  delivery_status?: string;
  telegram_sent?: boolean;
  desktop_sent?: boolean;
  sound_played?: boolean;
  user_marked_as_taken?: boolean;
  user_notes?: string;
  user_action?: string;
};

export async function getWatchlist() {
  return liveGet<{ status: string; items: WatchlistItem[]; settings?: AlertSettings }>('/api/watchlist');
}

export async function addWatchlistItem(payload: Partial<WatchlistItem> & { symbol: string }) {
  const response = await client.post('/api/watchlist', payload);
  clearApiCache();
  return response.data as { status: string; item: WatchlistItem; items?: WatchlistItem[] };
}

export async function updateWatchlistItem(symbol: string, payload: Partial<WatchlistItem>) {
  const response = await client.put(`/api/watchlist/${encodeURIComponent(symbol)}`, payload);
  clearApiCache();
  return response.data as { status: string; item: WatchlistItem };
}

export async function deleteWatchlistItem(symbol: string) {
  const response = await client.delete(`/api/watchlist/${encodeURIComponent(symbol)}`);
  clearApiCache();
  return response.data as { status: string; removed: boolean; symbol: string };
}

export async function getWatchlistStatus() {
  return liveGet<{ status: string; monitor: Record<string, unknown>; count: number }>('/api/watchlist/status');
}

export function getWatchlistStreamUrl() {
  return `${getApiBaseUrl()}/api/watchlist/stream`;
}

export async function getAlertHistory(params: Record<string, string | number | undefined> = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') query.set(key, String(value));
  });
  return liveGet<{ status: string; alerts: AlertHistoryRecord[] }>(`/api/alerts${query.toString() ? `?${query}` : ''}`);
}

export async function getWatchlistHistory(params: Record<string, string | number | undefined> = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') query.set(key, String(value));
  });
  return liveGet<{ status: string; alerts: AlertHistoryRecord[] }>(`/api/watchlist/history${query.toString() ? `?${query}` : ''}`);
}

export type WatchlistAuditRecord = {
  audit_id: string;
  symbol: string;
  company_name: string;
  outcome: 'Target Hit' | 'Stoploss Hit';
  entry_price: number;
  exit_price: number;
  stop_loss: number;
  target1: number;
  target2: number;
  target3: number;
  profit_loss_pct: number;
  volume_spike?: number;
  trade_reason?: string;
  entered_at: string;
  archived_at: string;
  hit_details?: string;
  suggested_time?: string;
};

export async function clearWatchlistHistory() {
  const response = await client.delete('/api/watchlist/history');
  clearApiCache();
  return response.data as { status: string; message: string };
}

export async function getWatchlistAudit(params: Record<string, string | number | undefined> = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') query.set(key, String(value));
  });
  return liveGet<{ status: string; audit: WatchlistAuditRecord[] }>(`/api/watchlist/audit${query.toString() ? `?${query}` : ''}`);
}

export async function clearWatchlistAudit() {
  const response = await client.delete('/api/watchlist/audit');
  clearApiCache();
  return response.data as { status: string; message: string };
}

export async function getAlertSettings() {
  return liveGet<{ status: string; settings: AlertSettings }>('/api/alerts/settings');
}

export async function saveAlertSettings(payload: AlertSettings) {
  const response = await client.put('/api/alerts/settings', payload);
  clearApiCache();
  return response.data as { status: string; settings: AlertSettings };
}

export async function testBackendAlert(payload: Record<string, unknown>) {
  const response = await client.post('/api/alerts/test', payload);
  clearApiCache();
  return response.data as { status: string; alert: AlertHistoryRecord };
}

export async function testTelegramAlert(payload: Record<string, unknown>) {
  const response = await client.post('/api/telegram/test', payload);
  return response.data as { status: string; telegram?: unknown; message?: string };
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
    scan_mode: row.scan_mode,
    scan_family: row.scan_family,
    scanner_bucket: row.scanner_bucket,
    pipeline_stage: row.pipeline_stage,
    scanner_display_name: row.scanner_display_name,
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
  horizon?: 'intraday' | 'swing';
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
  const horizonFiltered = options.horizon
    ? normalized.filter((row: any) => {
      const text = `${row.scan_family || ''} ${row.scanner_bucket || ''} ${row.pipeline_stage || ''} ${row.best_horizon || ''} ${row.tag || ''} ${row.scan_mode || ''} ${row.category || ''}`.toLowerCase();
      if (options.horizon === 'intraday') return text.includes('intraday') || text.includes('premarket') || text.includes('market-open') || text.includes('open_confirmation') || text.includes('open-confirmation');
      return text.includes('swing');
    })
    : normalized;
  return options.actionableOnly === false ? horizonFiltered : horizonFiltered.filter(isActionableStock);
}

export async function getLatestScanWithResults(options: ExtractOptions & { scanMode?: string | RegExp } = {}) {
  const list = await listScans();
  const scans = (list?.scans || []).filter((scan: any) => {
    if (!(scan.scan_id || scan.id)) return false;
    if (!options.scanMode) return true;
    const mode = `${scan.scan_family || ''} ${scan.scanner_bucket || ''} ${scan.pipeline_stage || ''} ${scan.scan_mode || scan.scan_type || scan.type || ''}`;
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
  return (list?.scans || []).filter((scan: any) => scan.scan_id || scan.id);
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
  addOptimisticActiveScan(response.data);
  return response.data;
}

export async function runDedicatedScan(family: 'premarket' | 'open-confirmation' | 'intraday', payload: ScanPayload = {}) {
  const response = await client.post(`/api/scans/${family}/run`, payload);
  clearApiCache();
  return response.data;
}

export async function getDedicatedScanLatest(family: 'premarket' | 'open-confirmation' | 'intraday') {
  return liveGet(`/api/scans/${family}/latest`);
}

export async function getPipelineToday() {
  return liveGet('/api/scans/pipeline/today');
}

export async function preparePipelineStage(stage: 'open-confirmation' | 'intraday', payload: Record<string, unknown> = {}) {
  const response = await client.post('/api/scans/pipeline/prepare', { ...payload, stage });
  return response.data;
}

export async function runMetaScanner(timeframe = 'intraday') {
  const response = await client.post('/api/meta-scanner/run', { timeframe });
  clearApiCache();
  return response.data;
}

export async function getMetaScannerLatest(timeframe = 'intraday') {
  return liveGet(`/api/meta-scanner/latest?timeframe=${encodeURIComponent(timeframe)}`);
}

export async function getMetaScannerConflicts() {
  return liveGet('/api/meta-scanner/conflicts');
}

export async function getMetaScannerAgreements() {
  return liveGet('/api/meta-scanner/agreements');
}

export async function getFinalDecisions(timeframe = 'intraday') {
  return liveGet(`/api/final-decisions/latest?timeframe=${encodeURIComponent(timeframe)}`);
}

export async function getMlPredictions(timeframe = 'intraday') {
  return liveGet(`/api/ml/predictions?timeframe=${encodeURIComponent(timeframe)}`);
}

export async function getGrowwIntradayStocks(limit = 80) {
  return liveGet(`/api/sources/groww/intraday?limit=${limit}`);
}

export async function analyzeGrowwIntradayStocks(limit = 80, interval = '5m', cacheSeconds = 90) {
  return liveGet(`/api/sources/groww/intraday/analyze?limit=${limit}&interval=${encodeURIComponent(interval)}&cache_seconds=${cacheSeconds}`);
}

export async function stopScan(scanId: string) {
  const response = await client.post('/api/scan/stop', { scan_id: scanId });
  clearApiCache();
  removeOptimisticActiveScan(scanId);
  return response.data;
}

export async function stopAllScans() {
  const response = await client.post('/api/scan/stop-all');
  clearApiCache();
  removeOptimisticActiveScan();
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

export async function getRealtimeSnapshot() {
  return liveGet('/api/realtime/snapshot');
}

export async function getOpportunities(kind = 'top', limit = 50) {
  return liveGet(`/api/opportunities/${encodeURIComponent(kind)}?limit=${limit}`);
}

export async function getLiveDashboard() {
  return liveGet('/api/dashboard/live');
}

export async function getScannerLatest(scanType: string) {
  return liveGet(`/api/scanners/${encodeURIComponent(scanType)}/latest`);
}

export async function getStockAnalysis(symbol: string, scanType = 'intraday') {
  return liveGet(`/api/stocks/${encodeURIComponent(symbol)}/analysis?scan_type=${encodeURIComponent(scanType)}`);
}

export async function getStockTradePlan(symbol: string, scanType = 'intraday') {
  return liveGet(`/api/stocks/${encodeURIComponent(symbol)}/trade-plan?scan_type=${encodeURIComponent(scanType)}`);
}

export async function getStockMlPrediction(symbol: string, timeframe = 'intraday') {
  return liveGet(`/api/ml/predictions/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(timeframe)}`);
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

export async function getAiMarketSummary() {
  return liveGet('/api/ai/market-summary');
}

export async function getAiStockInsight(symbol: string, scanType = '') {
  const suffix = scanType ? `?scan_type=${encodeURIComponent(scanType)}` : '';
  return liveGet(`/api/ai/stock/${encodeURIComponent(symbol)}/insight${suffix}`);
}

export async function getAiTradePlan(symbol: string, scanType = '') {
  const suffix = scanType ? `?scan_type=${encodeURIComponent(scanType)}` : '';
  return liveGet(`/api/ai/stock/${encodeURIComponent(symbol)}/trade-plan${suffix}`);
}

export async function getAiScannerInsights(scanType: string) {
  return liveGet(`/api/ai/scanner/${encodeURIComponent(scanType)}/insights`);
}

export async function askAiCopilot(query: string) {
  const response = await client.post('/api/ai/copilot/query', { query });
  return response.data;
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
