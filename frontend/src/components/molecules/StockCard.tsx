"use client";
import React, { memo, useState } from 'react';
import { useDispatch } from 'react-redux';
import { ArrowRightLeft, BarChart3, FileDown, GitCompare, Pin, Star, Telescope } from 'lucide-react';
import { addSymbol } from '@/state/watchlistSlice';

export type StockRecord = {
  stock?: string;
  symbol?: string;
  sector?: string;
  industry?: string;
  live_price?: number;
  entry_price?: number;
  stop_loss?: number;
  target1?: number;
  target2?: number;
  target3?: number;
  rrr?: string;
  expected_return?: number;
  stop_distance_pct?: number;
  ml_score?: number;
  technical_score?: number;
  profitability_score?: number;
  quality_score?: number;
  fundamental_score?: number;
  confidence_pct?: number;
  data_reliability_score?: number;
  volume_strength?: string;
  breakout_strength?: string;
  pattern?: string;
  trend?: string;
  action?: string;
  reason?: string;
  quality_filter_passed?: boolean;
  quality_filter_reasons?: string;
  generated_at?: string;
  last_updated?: string;
  tag?: string;
  change?: number;
  gapPercent?: number;
  risk_score?: number;
  reward_potential?: number;
};

const dash = '-';

function formatPrice(value?: number) {
  if (typeof value !== 'number') return dash;
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(value);
}

function score(value?: number) {
  if (typeof value !== 'number') return dash;
  if (Math.abs(value) <= 1) return `${Math.round(value * 100)}%`;
  return `${Math.round(value)}%`;
}

function pct(value?: number) {
  if (typeof value !== 'number') return dash;
  return `${value.toFixed(value >= 10 ? 0 : 1)}%`;
}

function StockCardComponent({ item }: { item: StockRecord }) {
  const dispatch = useDispatch();
  const [expanded, setExpanded] = useState(false);
  const symbol = item.symbol || item.stock || 'UNKNOWN';
  const action = String(item.action || 'WATCH').toUpperCase();
  const isPositive = (item.change || item.gapPercent || 0) >= 0;

  function handlePin() {
    if (symbol) dispatch(addSymbol(symbol));
  }

  return (
    <article className={`stock-card stock-card--${action.toLowerCase().replace(/\s+/g, '-')}`}>
      <header className="stock-card__header">
        <div>
          <div className="stock-card__symbol">{symbol}</div>
          <div className="stock-card__sector">{item.stock || symbol} - {item.sector || 'Unclassified'}</div>
        </div>
        <span className={`signal-pill signal-pill--${action.toLowerCase()}`}>{action}</span>
      </header>

      <button className="stock-card__price-row" type="button" onClick={() => setExpanded((value) => !value)}>
        <span>INR {formatPrice(item.live_price)}</span>
        <strong className={isPositive ? 'tone-good' : 'tone-bad'}>
          {isPositive ? '+' : ''}{typeof item.change === 'number' ? item.change.toFixed(2) : (item.gapPercent || 0).toFixed(2)}%
        </strong>
      </button>

      <div className="stock-card__levels">
        <span><b>Entry</b>{formatPrice(item.entry_price)}</span>
        <span><b>SL</b>{formatPrice(item.stop_loss)}</span>
        <span><b>T1</b>{formatPrice(item.target1)}</span>
        <span><b>T2</b>{formatPrice(item.target2)}</span>
        <span><b>T3</b>{formatPrice(item.target3)}</span>
        <span><b>RRR</b>{item.rrr || dash}</span>
      </div>

      <div className="stock-card__scores">
        <span>ML {score(item.ml_score)}</span>
        <span>Tech {score(item.technical_score)}</span>
        <span>Profit {score(item.profitability_score)}</span>
        <span>Quality {score(item.quality_score)}</span>
        <span>Fund {score(item.fundamental_score)}</span>
        <span>Conf {score(item.confidence_pct)}</span>
        <span>Data {score(item.data_reliability_score)}</span>
      </div>

      <div className="stock-card__meta">
        <span>Expected {pct(item.expected_return)}</span>
        <span>Stop {pct(item.stop_distance_pct)}</span>
        <span>Vol {item.volume_strength || dash}</span>
        <span>Breakout {item.breakout_strength || dash}</span>
        <span>{item.trend || 'Trend pending'}</span>
      </div>

      {expanded && (
        <div className="stock-card__expanded">
          <p>{item.reason || item.quality_filter_reasons || 'Detailed model rationale will appear when the backend returns recommendation notes.'}</p>
          <dl>
            <div><dt>Pattern</dt><dd>{item.pattern || dash}</dd></div>
            <div><dt>Filter</dt><dd>{item.quality_filter_passed === false ? item.quality_filter_reasons || 'Rejected' : 'Passed'}</dd></div>
            <div><dt>Generated</dt><dd>{item.generated_at || dash}</dd></div>
            <div><dt>Updated</dt><dd>{item.last_updated || dash}</dd></div>
          </dl>
        </div>
      )}

      <footer className="stock-card__actions">
        <button className="icon-button" onClick={handlePin} title="Pin to watchlist" type="button"><Pin size={16} /></button>
        <button className="icon-button" title="Push to intraday" type="button"><ArrowRightLeft size={16} /></button>
        <button className="icon-button" title="Push to swing" type="button"><Star size={16} /></button>
        <button className="icon-button" title="Compare stocks" type="button"><GitCompare size={16} /></button>
        <button className="icon-button" title="Open detailed analysis" type="button"><Telescope size={16} /></button>
        <button className="icon-button" title="Export report" type="button"><FileDown size={16} /></button>
        <button className="icon-button" title="View chart" type="button"><BarChart3 size={16} /></button>
      </footer>
    </article>
  );
}

export const StockCard = memo(StockCardComponent);
export default StockCard;
