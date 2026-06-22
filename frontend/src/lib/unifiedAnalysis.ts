import { getLiveStockAnalysis, type StockAnalysisPayload, type StockTradePlan } from '@/lib/api';

export type AnalysisHorizon = 'intraday' | 'swing';

export function stockSymbol(row: any) {
  const raw = String(row?.symbol || row?.stock || row?.ticker || '').trim().toUpperCase();
  if (!raw) return '';
  return raw.includes('.') ? raw : `${raw}.NS`;
}

function planFor(analysis: StockAnalysisPayload, horizon: AnalysisHorizon): StockTradePlan {
  return (horizon === 'intraday'
    ? (analysis.intraday?.tradePlan || analysis.intraday_trade_plan)
    : (analysis.swing?.tradePlan || analysis.swing_trade_plan)) || {} as StockTradePlan;
}

export function recommendationFor(analysis: StockAnalysisPayload, horizon: AnalysisHorizon) {
  const canonical = horizon === 'intraday' ? analysis.intraday?.recommendation : analysis.swing?.recommendation;
  return String(canonical || (horizon === 'intraday' ? analysis.intraday_view : analysis.swing_view) || 'AVOID').toUpperCase();
}

export function applyUnifiedAnalysis(row: any, analysis: StockAnalysisPayload, horizon: AnalysisHorizon) {
  const plan = planFor(analysis, horizon);
  const recommendation = recommendationFor(analysis, horizon);
  const noTrade = recommendation === 'AVOID' || plan.status === 'no_trade';
  const targets = noTrade ? [] : analysis[horizon]?.targets || [plan.target1, plan.target2, plan.target3].filter((value) => value != null);
  const reason = analysis[horizon]?.reasons?.join(' ') || plan.reason || analysis.finalExplanation || analysis.reason || 'Backend analysis reason unavailable';
  const symbol = stockSymbol(row) || analysis.symbol;
  const entry = noTrade ? null : analysis[horizon]?.entry ?? plan.entry_price ?? plan.entry_trigger ?? null;
  const stopLoss = noTrade ? null : analysis[horizon]?.stopLoss ?? plan.stop_loss ?? null;
  return {
    ...row,
    symbol,
    stock: symbol,
    live_price: analysis.quote?.current_price ?? row?.live_price ?? row?.current_price ?? row?.ltp,
    current_price: analysis.quote?.current_price ?? row?.current_price ?? row?.live_price ?? row?.ltp,
    entry_price: entry,
    entry,
    stop_loss: stopLoss,
    stoploss: stopLoss,
    target1: targets[0] ?? null,
    target2: targets[1] ?? null,
    target3: targets[2] ?? null,
    expected_return: noTrade ? 0 : row?.expected_return,
    priority_profit_pct: noTrade ? 0 : row?.priority_profit_pct,
    risk_reward: noTrade ? null : plan.risk_reward_ratio ?? row?.risk_reward,
    action: recommendation,
    signal: recommendation,
    ai_rating: recommendation,
    reason,
    recommendation_reason: reason,
    confidence_pct: analysis[horizon]?.confidence ?? analysis.confidence ?? row?.confidence_pct,
    final_ai_score: analysis.overallScore ?? row?.final_ai_score,
    risk: analysis.risk ?? row?.risk,
    breakout_status: analysis.breakout?.status ?? analysis.breakout_status,
    trend: analysis.trend,
    analysis_version: analysis.analysisVersion,
    settings_version: analysis.settingsVersion,
    analysis_updated_at: analysis.lastUpdated ?? analysis.generated_at,
    analysis_stale: analysis.isStale ?? analysis.stale,
    canonical_analysis: analysis,
    canonical_horizon: horizon,
  };
}

export async function hydrateRowsWithUnifiedAnalysis(rows: any[], horizon: AnalysisHorizon, limit = 30) {
  const selected = rows.slice(0, limit);
  const hydrated: any[] = [];
  for (let index = 0; index < selected.length; index += 6) {
    const batch = selected.slice(index, index + 6);
    const batchRows = await Promise.all(batch.map(async (row) => {
      const symbol = stockSymbol(row);
      if (!symbol) return row;
      try {
        return applyUnifiedAnalysis(row, await getLiveStockAnalysis(symbol, horizon), horizon);
      } catch {
        return { ...row, analysis_unavailable: true };
      }
    }));
    hydrated.push(...batchRows);
  }
  return [...hydrated, ...rows.slice(limit)];
}

export function applyUnifiedMasterAnalysis(row: any, analysis: StockAnalysisPayload) {
  const symbol = stockSymbol(row) || analysis.symbol;
  const recommendation = String(analysis.masterRecommendation || 'AVOID').toUpperCase();
  return {
    ...row,
    symbol,
    stock: symbol,
    live_price: analysis.quote?.current_price ?? row?.live_price ?? row?.current_price,
    current_price: analysis.quote?.current_price ?? row?.current_price ?? row?.live_price,
    action: recommendation,
    signal: recommendation,
    ai_rating: recommendation,
    final_ai_score: analysis.overallScore ?? row?.final_ai_score,
    confidence_pct: analysis.confidence ?? row?.confidence_pct,
    reason: analysis.finalExplanation || analysis.reason || row?.reason,
    analysis_version: analysis.analysisVersion,
    settings_version: analysis.settingsVersion,
    analysis_updated_at: analysis.lastUpdated ?? analysis.generated_at,
    analysis_stale: analysis.isStale ?? analysis.stale,
    canonical_analysis: analysis,
    canonical_horizon: 'master',
  };
}

export async function hydrateRowsWithMasterAnalysis(rows: any[], limit = 30) {
  const selected = rows.slice(0, limit);
  const hydrated: any[] = [];
  for (let index = 0; index < selected.length; index += 6) {
    const batch = selected.slice(index, index + 6);
    const batchRows = await Promise.all(batch.map(async (row) => {
      const symbol = stockSymbol(row);
      if (!symbol) return row;
      try {
        return applyUnifiedMasterAnalysis(row, await getLiveStockAnalysis(symbol, 'all'));
      } catch {
        return { ...row, analysis_unavailable: true };
      }
    }));
    hydrated.push(...batchRows);
  }
  return [...hydrated, ...rows.slice(limit)];
}
