"use client";

import React, { useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Bell, Bookmark, RefreshCw, TerminalSquare } from 'lucide-react';
import {
  addV20WatchlistItem,
  createV20Alert,
  getLiveStockAnalysis,
  getStockCandles,
  getStockDetail,
  getStockStreamUrl,
  type StockAnalysisPayload,
  type StockCandle,
  type StockQuotePayload,
  type StockTradePlan,
} from '@/lib/api';

const ranges = ['1D', '1W', '1M', '3M', '6M', '1Y', '3Y', '5Y', 'ALL'];

function money(value?: number | null) {
  if (value === null || value === undefined) return 'Data unavailable';
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 'Data unavailable';
  return `INR ${new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(numeric)}`;
}

function numberText(value?: number | null, digits = 2) {
  if (value === null || value === undefined) return '-';
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return '-';
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: digits }).format(numeric);
}

function statusClass(value?: string) {
  const upper = String(value || '').toUpperCase();
  if (upper.includes('BUY') || upper.includes('BULL') || upper.includes('BREAKOUT')) return 'good';
  if (upper.includes('WATCH') || upper.includes('SIDEWAYS') || upper.includes('ABOUT')) return 'warn';
  return 'bad';
}

function Chart({ candles }: { candles: StockCandle[] }) {
  const points = useMemo(() => {
    const rows = candles.filter((row) => Number.isFinite(Number(row.close))).slice(-180);
    if (rows.length < 2) return '';
    const closes = rows.map((row) => Number(row.close));
    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const spread = max - min || 1;
    return rows
      .map((row, index) => {
        const x = (index / Math.max(rows.length - 1, 1)) * 1000;
        const y = 260 - ((Number(row.close) - min) / spread) * 220;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(' ');
  }, [candles]);

  if (!points) {
    return <div className="stock-chart-empty">Candle data unavailable</div>;
  }

  return (
    <svg className="stock-chart" viewBox="0 0 1000 300" role="img" aria-label="Stock price chart">
      <defs>
        <linearGradient id="stockLine" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor="#48d59b" />
          <stop offset="60%" stopColor="#66d9ff" />
          <stop offset="100%" stopColor="#9b8cff" />
        </linearGradient>
      </defs>
      <polyline fill="none" stroke="url(#stockLine)" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" points={points} />
    </svg>
  );
}

function SignalCard({ title, value, detail }: { title: string; value?: string; detail?: string }) {
  return (
    <article className={`analysis-card analysis-card--${statusClass(value)}`}>
      <span>{title}</span>
      <strong>{value || 'Data unavailable'}</strong>
      {detail && <small>{detail}</small>}
    </article>
  );
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="analysis-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function TradePlanCard({ title, plan }: { title: string; plan?: StockTradePlan }) {
  return (
    <article className={`trade-plan-card trade-plan-card--${statusClass(plan?.signal)}`}>
      <header>
        <span>{title}</span>
        <strong>{plan?.signal || 'Data unavailable'}</strong>
        <small>{plan?.valid_for || 'Backend plan unavailable'}</small>
      </header>
      <div className="trade-plan-metrics">
        <Metric label="Entry" value={money(plan?.entry_price)} />
        <Metric label="Stop Loss" value={money(plan?.stop_loss)} />
        <Metric label="Target 1" value={money(plan?.target1)} />
        <Metric label="Target 2" value={money(plan?.target2)} />
        <Metric label="Target 3" value={money(plan?.target3)} />
        <Metric label="Risk Reward" value={numberText(plan?.risk_reward_ratio)} />
      </div>
      <p>{plan?.reason || 'No backend reason available for this horizon.'}</p>
    </article>
  );
}

function LegacyPlanNotice({ analysis }: { analysis: StockAnalysisPayload | null }) {
  const hasSplitPlans = Boolean(analysis?.intraday_trade_plan || analysis?.swing_trade_plan);
  const hasLegacyPlan = Boolean(
    !hasSplitPlans
    && (analysis?.entry_price || analysis?.stop_loss || analysis?.target1 || analysis?.target2 || analysis?.target3)
  );
  if (!hasLegacyPlan) return null;
  return (
    <article className="legacy-plan-notice">
      <strong>Legacy general backend plan</strong>
      <span>
        This payload is not marked as Intraday or Swing. Restart the backend/frontend so the newer
        `intraday_trade_plan` and `swing_trade_plan` fields are returned.
      </span>
      <div className="trade-plan-metrics">
        <Metric label="Entry" value={money(analysis?.entry_price)} />
        <Metric label="Stop Loss" value={money(analysis?.stop_loss)} />
        <Metric label="Target 1" value={money(analysis?.target1)} />
        <Metric label="Target 2" value={money(analysis?.target2)} />
        <Metric label="Target 3" value={money(analysis?.target3)} />
        <Metric label="Risk Reward" value={numberText(analysis?.risk_reward_ratio)} />
      </div>
    </article>
  );
}

export default function StockDetailPage() {
  const params = useParams<{ symbol: string }>();
  const router = useRouter();
  const symbol = useMemo(() => decodeURIComponent(String(params.symbol || '')).toUpperCase(), [params.symbol]);
  const [range, setRange] = useState('1D');
  const [stock, setStock] = useState<StockQuotePayload | null>(null);
  const [analysis, setAnalysis] = useState<StockAnalysisPayload | null>(null);
  const [candles, setCandles] = useState<StockCandle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [connection, setConnection] = useState<'connecting' | 'live' | 'offline'>('connecting');
  const [actionMessage, setActionMessage] = useState('');

  async function load(selectedRange = range) {
    if (!symbol) return;
    setLoading(true);
    setError('');
    try {
      const [stockPayload, analysisPayload, candlePayload] = await Promise.all([
        getStockDetail(symbol),
        getLiveStockAnalysis(symbol),
        getStockCandles(symbol, selectedRange),
      ]);
      setStock(stockPayload);
      setAnalysis(analysisPayload);
      setCandles(candlePayload.candles || []);
    } catch (err: any) {
      setError(err?.response?.data?.message || err?.message || 'Stock data unavailable');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(range);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, range]);

  useEffect(() => {
    if (!symbol || typeof window === 'undefined') return undefined;
    setConnection('connecting');
    const stream = new EventSource(getStockStreamUrl(symbol));
    stream.addEventListener('open', () => setConnection('live'));
    stream.addEventListener('error', () => setConnection('offline'));
    stream.addEventListener('QUOTE_UPDATED', (event) => {
      try {
        setStock(JSON.parse((event as MessageEvent).data));
        setConnection('live');
      } catch {
        setConnection('offline');
      }
    });
    stream.addEventListener('ANALYSIS_UPDATED', (event) => {
      try {
        setAnalysis(JSON.parse((event as MessageEvent).data));
        setConnection('live');
      } catch {
        setConnection('offline');
      }
    });
    return () => stream.close();
  }, [symbol]);

  async function addWatchlist() {
    setActionMessage('');
    try {
      await addV20WatchlistItem(symbol);
      setActionMessage(`${symbol} added to watchlist`);
    } catch (err: any) {
      setActionMessage(err?.message || 'Watchlist update failed');
    }
  }

  async function createPriceAlert() {
    setActionMessage('');
    const current = Number(stock?.quote?.current_price || analysis?.quote?.current_price);
    if (!Number.isFinite(current) || current <= 0) {
      setActionMessage('Alert unavailable until live price loads');
      return;
    }
    try {
      await createV20Alert({ symbol, alert_type: 'price_cross', condition: 'near_current_price', threshold: current });
      setActionMessage(`Alert created near ${money(current)}`);
    } catch (err: any) {
      setActionMessage(err?.message || 'Alert creation failed');
    }
  }

  const quote = stock?.quote || analysis?.quote || {};
  const change = Number(quote.change || 0);
  const changePct = Number(quote.change_pct || 0);
  const lastUpdated = analysis?.lastUpdated || stock?.updated_at || quote.updated_at || analysis?.generated_at;

  return (
    <main className="stock-detail-page">
      <section className="stock-detail-hero">
        <div className="stock-logo-large">{symbol.slice(0, 1)}</div>
        <div className="stock-title-block">
          <span>{stock?.exchange || 'NSE'} - {symbol}</span>
          <h1>{stock?.name || analysis?.stock?.name || symbol}</h1>
          <div className="stock-price-row">
            <strong>{money(Number(quote.current_price))}</strong>
            <em className={change >= 0 ? 'status-good' : 'status-bad'}>
              {change >= 0 ? '+' : ''}{numberText(change)} ({changePct >= 0 ? '+' : ''}{numberText(changePct)}%)
            </em>
          </div>
          <small>
            Last refreshed {lastUpdated || 'Data unavailable'} - Data source {stock?.source || 'backend provider'}
            {stock?.stale || analysis?.stale ? ' - stale cache' : ''}
          </small>
        </div>
        <div className="stock-action-row">
          <button type="button" onClick={addWatchlist}><Bookmark size={16} /> Watchlist</button>
          <button type="button" onClick={createPriceAlert}><Bell size={16} /> Alert</button>
          <button type="button" onClick={() => router.push(`/intraday?symbol=${encodeURIComponent(symbol)}`)}><TerminalSquare size={16} /> Terminal</button>
          <button type="button" onClick={() => load(range)}><RefreshCw size={16} /> Retry</button>
        </div>
      </section>

      {actionMessage && <div className="stock-action-message">{actionMessage}</div>}
      <div className={`stream-status stream-status--${connection}`}>Realtime {connection}</div>

      {loading && <div className="stock-skeleton">Loading live stock data and backend analysis...</div>}
      {error && (
        <div className="stock-error">
          <strong>{error}</strong>
          <button type="button" onClick={() => load(range)}>Retry</button>
        </div>
      )}

      <section className="stock-chart-card">
        <div className="timeframe-strip">
          {ranges.map((item) => (
            <button className={range === item ? 'active' : ''} key={item} type="button" onClick={() => setRange(item)}>
              {item}
            </button>
          ))}
        </div>
        <Chart candles={candles} />
      </section>

      <section className="analysis-summary-grid">
        <SignalCard title="Master View" value={analysis?.masterRecommendation} detail={`Overall score ${numberText(analysis?.overallScore)} - ${analysis?.risk || 'risk unavailable'}`} />
        <SignalCard title="Intraday View" value={analysis?.intraday?.recommendation || analysis?.intraday_view} detail="Same-day recommendation from unified backend analysis" />
        <SignalCard title="Swing View" value={analysis?.swing?.recommendation || analysis?.swing_view} detail="Multi-day recommendation from unified backend analysis" />
        <SignalCard title="Breakout" value={analysis?.breakout?.status || analysis?.breakout_status} detail="Resistance and volume confirmation" />
        <SignalCard title="Trend" value={analysis?.trend} detail="EMA alignment from backend" />
      </section>

      <section className="stock-analysis-panel">
        <header>
          <span>Backend Analysis</span>
          <h2>Separate Intraday And Swing Trade Plans</h2>
        </header>
        <div className="trade-plan-split">
          <TradePlanCard title="Intraday Trade Plan" plan={analysis?.intraday_trade_plan} />
          <TradePlanCard title="Swing Trade Plan" plan={analysis?.swing_trade_plan} />
        </div>
        <LegacyPlanNotice analysis={analysis} />
        <header>
          <span>Indicators</span>
          <h2>Technical Context</h2>
        </header>
        <div className="analysis-metric-grid">
          <Metric label="Support" value={(analysis?.support_levels || []).map((value) => numberText(value)).join(' / ') || 'Data unavailable'} />
          <Metric label="Resistance" value={(analysis?.resistance_levels || []).map((value) => numberText(value)).join(' / ') || 'Data unavailable'} />
          <Metric label="RSI" value={numberText(analysis?.indicators?.rsi)} />
          <Metric label="MACD" value={numberText(analysis?.indicators?.macd?.macd)} />
          <Metric label="EMA 20" value={money(analysis?.indicators?.ema20)} />
          <Metric label="EMA 50" value={money(analysis?.indicators?.ema50)} />
          <Metric label="EMA 200" value={money(analysis?.indicators?.ema200)} />
          <Metric label="VWAP" value={money(analysis?.indicators?.vwap)} />
          <Metric label="Gap" value={`${analysis?.gap_status?.label || 'Data unavailable'} (${numberText(analysis?.gap_status?.gap_pct)}%)`} />
          <Metric label="Volume" value={`${analysis?.volume_analysis?.label || 'Data unavailable'} - ${numberText(analysis?.volume_analysis?.relative_volume)}x`} />
          <Metric label="Delivery Strength" value={analysis?.delivery_strength || 'Data unavailable'} />
        </div>
        <article className="analysis-reason">
          <span>Reason</span>
          <p>{analysis?.finalExplanation || analysis?.reason || analysis?.message || 'Analysis reason unavailable from backend.'}</p>
          <small>
            {analysis?.analysisVersion || 'analysis version unavailable'} - settings {analysis?.settingsVersion || 'unavailable'} - {analysis?.cache?.hit ? 'cache hit' : 'fresh calculation'} - age {numberText(analysis?.dataAgeSeconds)}s
          </small>
        </article>
      </section>
    </main>
  );
}
