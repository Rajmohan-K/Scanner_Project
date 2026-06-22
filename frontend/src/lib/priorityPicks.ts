export type PriorityHorizon = 'intraday' | 'swing' | 'groww';

export type PriorityPickOptions = {
  horizon?: PriorityHorizon;
  includeUnknown?: boolean;
  limit?: number;
  minProfitPct?: number;
  sourceName?: string;
};

export const PRIORITY_CANDIDATES_KEY = 'priority-picks-external-candidates-v1';
export const PRIORITY_CANDIDATES_EVENT = 'priority-picks-external-candidates-updated';
const defaultLimit = 5;
const defaultMinProfitPct = 3;

export function prioritySymbol(row: any) {
  return String(row?.symbol || row?.stock || row?.ticker || '').toUpperCase();
}

export function priorityNumber(value: unknown) {
  if (typeof value === 'number') return Number.isFinite(value) && value > 0 ? value : 0;
  if (typeof value !== 'string') return 0;
  const match = value.replace(/,/g, '').match(/-?\d+(?:\.\d+)?/);
  const numeric = match ? Number(match[0]) : 0;
  return Number.isFinite(numeric) && numeric > 0 ? numeric : 0;
}

function priorityNumbers(value: unknown) {
  if (typeof value === 'number') return Number.isFinite(value) && value > 0 ? [value] : [];
  if (typeof value !== 'string') {
    const numeric = priorityNumber(value);
    return numeric ? [numeric] : [];
  }
  return Array.from(value.replace(/,/g, '').matchAll(/-?\d+(?:\.\d+)?/g))
    .map((match) => Number(match[0]))
    .filter((numeric) => Number.isFinite(numeric) && numeric > 0);
}

export function priorityEntry(row: any) {
  return priorityNumber(row?.entry_price ?? row?.entry ?? row?.buy_above ?? row?.trigger_price ?? row?.live_price ?? row?.current_price ?? row?.last_close);
}

export function priorityStopLoss(row: any) {
  return priorityNumber(row?.stop_loss ?? row?.stoploss ?? row?.sl ?? row?.stop);
}

export function priorityTargets(row: any) {
  const targets = [
    ...priorityNumbers(row?.target1),
    ...priorityNumbers(row?.target_1),
    ...priorityNumbers(row?.target2),
    ...priorityNumbers(row?.target_2),
    ...priorityNumbers(row?.target3),
    ...priorityNumbers(row?.target_3),
    ...priorityNumbers(row?.targets),
    ...priorityNumbers(row?.target),
  ];
  return Array.from(new Set(targets)).filter((target) => target > 0).sort((a, b) => a - b);
}

export function priorityProfitPct(row: any) {
  const directValues = [
    row?.priority_profit_pct,
    row?.expected_return,
    row?.expected_profit_pct,
    row?.profit_pct,
    row?.profit_percent,
  ]
    .map(priorityNumber)
    .filter((value) => value > 0 && value <= 100);
  const entry = priorityEntry(row);
  const targetValues = priorityTargets(row).filter((target) => entry && target > entry);
  const fromTargets = targetValues.length ? Math.max(...targetValues.map((target) => ((target - entry) / entry) * 100)) : 0;
  return Math.max(fromTargets, ...directValues, 0);
}

export function priorityRiskReward(row: any) {
  const entry = priorityEntry(row);
  const stop = priorityStopLoss(row);
  const firstTarget = priorityTargets(row).find((target) => target > entry) || 0;
  if (!entry || !stop || !firstTarget || entry <= stop) return 0;
  return Math.round(((firstTarget - entry) / (entry - stop)) * 100) / 100;
}

export function inferPriorityHorizon(row: any): PriorityHorizon | 'unknown' {
  const haystack = [
    row?.source,
    row?.source_name,
    row?.scan_type,
    row?.scan_family,
    row?.scanner_bucket,
    row?.scan_mode,
    row?.pipeline_stage,
    row?.horizon,
    row?.strategy,
    row?.setup_type,
    row?.interval,
    row?.sector,
    row?.reason,
  ].join(' ').toLowerCase();
  if (/groww|intraday|premarket|market[- ]?open|open[- ]?confirmation|vwap|scalp|5m|15m|1h/.test(haystack)) return 'intraday';
  if (/swing|multi[- ]?day|positional|daily|1d|holding|2-10 sessions|3-30/.test(haystack)) return 'swing';
  return 'unknown';
}

function priorityScore(row: any) {
  return priorityNumber(row?.confidence_pct ?? row?.final_ai_score ?? row?.intraday_score ?? row?.swing_score ?? row?.ml_score ?? row?.score ?? row?.profitability_score);
}

function scoreParts(row: any) {
  return [
    ['AI', row?.final_ai_score ?? row?.profitability_score],
    ['ML', row?.ml_score ?? row?.ml_probability],
    ['Tech', row?.technical_score],
    ['Confidence', row?.confidence_pct ?? row?.confidence],
    ['Quality', row?.quality_score],
    ['Data', row?.data_reliability_score],
  ]
    .map(([label, value]) => {
      const numeric = priorityNumber(value);
      return numeric ? `${label} ${numeric}` : '';
    })
    .filter(Boolean);
}

function backendReason(row: any) {
  const reason = row?.reason || row?.explanation || row?.trade_reason || row?.recommendation_reason || row?.quality_filter_reasons || row?.message;
  if (Array.isArray(reason)) return reason.join(', ');
  return String(reason || '').trim();
}

function suggestedTime(row: any, horizon?: PriorityHorizon) {
  if (row?.suggested_time || row?.entry_window || row?.trade_window) {
    return row?.suggested_time || row?.entry_window || row?.trade_window;
  }
  if (horizon === 'swing') return 'After daily close confirmation; review for 2-10 sessions';
  return 'After VWAP/volume confirmation; avoid fresh entry near close';
}

function suggestedEntryTimestamp(row: any) {
  return row?.suggested_entry_time || row?.entry_timestamp || row?.generated_at || row?.last_updated || row?.updated_at || row?.created_at || new Date().toISOString();
}

export function detailedPriorityReason(row: any, horizon: PriorityHorizon | 'unknown' | undefined, priorityProfit: number, riskReward: number, entry: number, stop: number, targets: number[]) {
  const label = horizon === 'swing' ? 'Swing' : 'Intraday';
  const targetText = targets.length ? targets.map((target) => `INR ${target.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`).join(', ') : 'target unavailable';
  const scoreText = scoreParts(row);
  const source = row?.source_name || row?.scanner_display_name || row?.scan_mode || row?.scan_type || row?.priority_source || 'scanner source';
  const baseReason = backendReason(row);
  const pieces = [
    `${label} priority selected because target potential is ${priorityProfit.toFixed(2)}% and the trade has a complete plan.`,
    `Entry INR ${entry.toLocaleString('en-IN', { maximumFractionDigits: 2 })}, stoploss INR ${stop.toLocaleString('en-IN', { maximumFractionDigits: 2 })}, targets ${targetText}.`,
    `Risk reward ${riskReward || '-'} from ${source}.`,
    scoreText.length ? `Scores: ${scoreText.join(', ')}.` : '',
    baseReason ? `Backend reason: ${baseReason}` : '',
  ];
  return pieces.filter(Boolean).join(' ');
}

function hasCompletePlan(row: any) {
  const entry = priorityEntry(row);
  const stop = priorityStopLoss(row);
  const targets = priorityTargets(row).filter((target) => target > entry);
  return Boolean(prioritySymbol(row) && entry && stop && targets.length);
}

export function buildPriorityRows(rows: any[], options: PriorityPickOptions = {}) {
  const minProfitPct = Number(options.minProfitPct ?? defaultMinProfitPct);
  const limit = Math.max(3, Math.min(5, Number(options.limit ?? defaultLimit)));
  const candidates = Array.from(rows || [])
    .filter(hasCompletePlan)
    .map((row) => {
      const inferred = inferPriorityHorizon(row);
      const effectiveHorizon = options.horizon || (inferred === 'unknown' ? undefined : inferred);
      const entry = priorityEntry(row);
      const stop = priorityStopLoss(row);
      const targets = priorityTargets(row).filter((target) => target > entry);
      const priorityProfit = Math.round(priorityProfitPct(row) * 100) / 100;
      const riskReward = priorityRiskReward(row);
      const richReason = detailedPriorityReason(row, effectiveHorizon || inferred, priorityProfit, riskReward, entry, stop, targets);
      return {
        ...row,
        symbol: prioritySymbol(row),
        source_name: row?.source_name || options.sourceName || (inferred === 'swing' ? 'Swing Scanner' : inferred === 'intraday' ? 'Intraday Scanner' : 'Scanner'),
        priority_horizon: effectiveHorizon || inferred,
        priority_source: inferred,
        priority_profit_pct: priorityProfit,
        risk_reward: riskReward,
        entry_price: entry,
        stop_loss: stop,
        target1: targets[0],
        target2: targets[1],
        target3: targets[2],
        suggested_time: suggestedTime(row, effectiveHorizon),
        suggested_entry_time: suggestedEntryTimestamp(row),
        priority_reason: richReason,
        detailed_priority_reason: richReason,
        _priorityScore: priorityScore(row),
      };
    })
    .filter((row) => {
      if (row.analysis_unavailable) return false;
      if (row.canonical_horizon && !/^BUY$/i.test(String(row.action || row.signal || ''))) return false;
      if (options.horizon) {
        const inferred = row.priority_source;
        if (inferred !== options.horizon && !(options.includeUnknown && inferred === 'unknown')) return false;
      }
      return row.priority_profit_pct >= minProfitPct;
    })
    .sort((a, b) => {
      const profitDiff = Number(b.priority_profit_pct || 0) - Number(a.priority_profit_pct || 0);
      if (profitDiff) return profitDiff;
      const scoreDiff = Number(b._priorityScore || 0) - Number(a._priorityScore || 0);
      if (scoreDiff) return scoreDiff;
      return Number(b.risk_reward || 0) - Number(a.risk_reward || 0);
    });

  const bySymbol = new Map<string, any>();
  candidates.forEach((row) => {
    if (!bySymbol.has(row.symbol)) bySymbol.set(row.symbol, row);
  });

  return Array.from(bySymbol.values())
    .slice(0, limit)
    .map((row, index) => {
      const { _priorityScore, ...cleanRow } = row;
      return { ...cleanRow, priority_rank: index + 1 };
    });
}

export function readPriorityCandidateRows() {
  if (typeof window === 'undefined') return [] as any[];
  try {
    const rows = JSON.parse(window.localStorage.getItem(PRIORITY_CANDIDATES_KEY) || '[]');
    return Array.isArray(rows) ? rows : [];
  } catch {
    return [];
  }
}

export function addPriorityCandidates(rows: any[], horizon: PriorityHorizon) {
  if (typeof window === 'undefined' || !rows.length) return { added: 0, rows: [] as any[] };
  const current = readPriorityCandidateRows();
  const byKey = new Map(current.map((row: any) => [`${row.priority_horizon || row.horizon || horizon}:${prioritySymbol(row)}`, row]));
  let added = 0;
  rows.forEach((row) => {
    const symbol = prioritySymbol(row);
    if (!symbol) return;
    const key = `${horizon}:${symbol}`;
    if (!byKey.has(key)) added += 1;
    byKey.set(key, {
      ...byKey.get(key),
      ...row,
      symbol,
      priority_horizon: horizon,
      horizon,
      source_name: row.source_name || (horizon === 'swing' ? 'Swing Monitor' : 'Intraday Monitor'),
      added_to_priority_at: new Date().toISOString(),
    });
  });
  const next = Array.from(byKey.values()).slice(0, 200);
  window.localStorage.setItem(PRIORITY_CANDIDATES_KEY, JSON.stringify(next));
  window.dispatchEvent(new CustomEvent(PRIORITY_CANDIDATES_EVENT, { detail: { rows: next, added } }));
  return { added, rows: next };
}
