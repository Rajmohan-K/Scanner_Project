"use client";
import React from 'react';
import { BellPlus, Target, X } from 'lucide-react';
import { TerminalPanel } from '@/components/terminal/TerminalPrimitives';

type GrowwPriorityPanelProps = {
  rows: any[];
  updatedAt?: string;
  eyebrow?: string;
  title?: string;
  emptyText?: string;
  onMonitor?: (row: any) => void;
};

const dash = '-';

function formatPrice(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return dash;
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(numeric);
}

function formatProfit(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return dash;
  return `${numeric.toFixed(2)}%`;
}

function symbolOf(row: any) {
  return row?.symbol || row?.stock || dash;
}

function signalOf(row: any) {
  return String(row?.action || row?.signal || row?.trade_type || 'WATCH').replace(/_/g, ' ').toUpperCase();
}

function reasonOf(row: any) {
  return row?.detailed_priority_reason || row?.priority_reason || row?.reason || row?.explanation || row?.trade_reason || row?.recommendation_reason || 'No detailed reason available yet.';
}

function formatUpdatedAt(value?: string) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return `Updated ${value}`;
  return `Updated ${date.toLocaleString('en-IN')}`;
}

export default function GrowwPriorityPanel({
  rows,
  updatedAt,
  eyebrow = 'Priority Picks',
  title = 'High Profit Priority Picks',
  emptyText = 'No priority stocks currently meet the profit threshold with complete entry, stoploss, and target levels.',
  onMonitor,
}: GrowwPriorityPanelProps) {
  const [selectedKey, setSelectedKey] = React.useState('');
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);
  const updatedText = mounted ? formatUpdatedAt(updatedAt) : '';
  return (
    <TerminalPanel
      eyebrow={eyebrow}
      title={title}
      actions={<span className="priority-updated" suppressHydrationWarning>{updatedText || 'Waiting for qualifying analysis'}</span>}
    >
      {rows.length ? (
        <div className="groww-priority-table">
          <div className="groww-priority-head">
            <span>Rank</span>
            <span>Symbol</span>
            <span>Profit</span>
            <span>Entry</span>
            <span>Stoploss</span>
            <span>Targets</span>
            <span>Suggested Time</span>
            <span>Signal</span>
            {onMonitor && <span>Action</span>}
          </div>
          {rows.map((row, index) => {
            const symbol = symbolOf(row);
            const rowKey = `${symbol}-${index}`;
            const selected = selectedKey === rowKey;
            return (
              <React.Fragment key={rowKey}>
                <button className={`groww-priority-row ${selected ? 'is-selected' : ''}`} type="button" onClick={() => setSelectedKey(selected ? '' : rowKey)}>
                  <span><b>#{row.priority_rank || index + 1}</b></span>
                  <span><strong>{symbol}</strong></span>
                  <span className="heat-good"><b>{formatProfit(row.priority_profit_pct ?? row.expected_return)}</b><small>RR {row.risk_reward || row.rrr || dash}</small></span>
                  <span>INR {formatPrice(row.entry_price ?? row.entry)}</span>
                  <span>INR {formatPrice(row.stop_loss ?? row.stoploss)}</span>
                  <span>INR {formatPrice(row.target1 ?? row.target_1)} / {formatPrice(row.target2 ?? row.target_2)}</span>
                  <span>{row.suggested_time || row.suggested_entry_time || dash}</span>
                  <span><b className={`signal-pill signal-pill--${signalOf(row).toLowerCase().replace(/\s+/g, '-')}`}>{signalOf(row)}</b></span>
                  {onMonitor && (
                    <span className="priority-row-actions" onClick={(event) => event.stopPropagation()}>
                      <button className="icon-button" type="button" title="Add to dashboard live monitor" onClick={() => onMonitor(row)}>
                        <BellPlus size={13} />
                      </button>
                    </span>
                  )}
                </button>
                {selected && (
                  <div 
                    className="custom-stock-detail-inline" 
                    onClick={(e) => e.stopPropagation()}
                    style={{ 
                      gridColumn: '1 / -1', 
                      background: 'rgba(10, 20, 35, 0.96)', 
                      borderTop: '1px solid var(--accent)', 
                      borderBottom: '1px solid var(--accent)', 
                      padding: '10px 14px',
                      color: 'var(--text)',
                      width: '100%',
                      boxSizing: 'border-box'
                    }}
                  >
                    <div style={{
                      position: 'sticky',
                      left: '20px',
                      maxWidth: '1200px',
                      width: '100%',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '8px',
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '6px' }}>
                        <h3 style={{ margin: 0, fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <strong style={{ color: 'var(--accent)' }}>{symbol}</strong>
                          <span style={{ fontSize: '0.78rem', color: 'var(--muted)' }}>Rank #{row.priority_rank || index + 1} | {row.sector || row.source_name || row.priority_source || 'Scanner'}</span>
                        </h3>
                        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                          {onMonitor && (
                            <button className="btn-secondary" type="button" onClick={() => onMonitor(row)} style={{ padding: '2px 6px', fontSize: '0.72rem', minHeight: '22px' }}>
                              <BellPlus size={11} /> Monitor
                            </button>
                          )}
                          <button className="btn-secondary" type="button" onClick={() => setSelectedKey('')} style={{ padding: '2px 6px', fontSize: '0.72rem', minHeight: '22px', background: 'rgba(255, 100, 100, 0.1)', color: '#ff6b6b', border: '1px solid rgba(255, 100, 100, 0.2)' }}>
                            Close
                          </button>
                        </div>
                      </div>

                      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1.1fr 0.9fr', gap: '16px' }}>
                        {/* Column 1: Analysis & Recommendation */}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                          <span style={{ fontSize: '0.62rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--accent)' }}>Analysis & Entry Window</span>
                          <p style={{ margin: 0, fontSize: '0.76rem', lineHeight: '1.35', color: 'var(--text)', opacity: 0.9 }}>
                            {reasonOf(row)}
                          </p>
                          <div style={{ fontSize: '0.74rem', color: 'var(--muted)' }}>
                            Suggested Entry Window: <strong style={{ color: 'var(--text)' }}>{row.suggested_time || row.suggested_entry_time || dash}</strong>
                          </div>
                        </div>

                        {/* Column 2: Key Levels & Targets */}
                        <div>
                          <span style={{ fontSize: '0.62rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--accent)', display: 'block', marginBottom: '4px' }}>Key Levels & Targets</span>
                          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 8px', fontSize: '0.74rem' }}>
                            <div>
                              <span style={{ fontSize: '0.6rem', color: 'var(--muted)', display: 'block' }}>Entry Price</span>
                              <strong>INR {formatPrice(row.entry_price ?? row.entry)}</strong>
                            </div>
                            <div>
                              <span style={{ fontSize: '0.6rem', color: 'var(--muted)', display: 'block' }}>Stop Loss</span>
                              <strong style={{ color: 'var(--negative)' }}>INR {formatPrice(row.stop_loss ?? row.stoploss)}</strong>
                            </div>
                            <div style={{ gridColumn: 'span 2' }}>
                              <span style={{ fontSize: '0.6rem', color: 'var(--muted)', display: 'block' }}>Targets (1 / 2 / 3)</span>
                              <strong>
                                {row.target1 || row.target_1 ? `INR ${formatPrice(row.target1 ?? row.target_1)}` : dash} / {row.target2 || row.target_2 ? `INR ${formatPrice(row.target2 ?? row.target_2)}` : dash} {row.target3 ? `/ INR ${formatPrice(row.target3)}` : ''}
                              </strong>
                            </div>
                          </div>
                        </div>

                        {/* Column 3: Source & Profit Stats */}
                        <div>
                          <span style={{ fontSize: '0.62rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--accent)', display: 'block', marginBottom: '4px' }}>Priority & Profit Stats</span>
                          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 8px', fontSize: '0.74rem' }}>
                            <div>
                              <span style={{ fontSize: '0.6rem', color: 'var(--muted)', display: 'block' }}>Expected Profit</span>
                              <strong style={{ color: 'var(--success)' }}>{formatProfit(row.priority_profit_pct ?? row.expected_return)}</strong>
                            </div>
                            <div>
                              <span style={{ fontSize: '0.6rem', color: 'var(--muted)', display: 'block' }}>Risk Reward (RRR)</span>
                              <strong>{row.risk_reward || row.rrr || dash}</strong>
                            </div>
                            <div>
                              <span style={{ fontSize: '0.6rem', color: 'var(--muted)', display: 'block' }}>Priority Rank</span>
                              <strong>#{row.priority_rank || index + 1}</strong>
                            </div>
                            <div>
                              <span style={{ fontSize: '0.6rem', color: 'var(--muted)', display: 'block' }}>Source Category</span>
                              <strong>{row.sector || row.source_name || row.priority_source || 'Scanner'}</strong>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      ) : (
        <div className="empty-inline">
          <Target size={16} /> {emptyText}
        </div>
      )}
    </TerminalPanel>
  );
}
