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
                  <span><strong>{symbol}</strong><small>{row.sector || row.source_name || row.priority_source || 'Scanner'}</small></span>
                  <span className="heat-good"><b>{formatProfit(row.priority_profit_pct ?? row.expected_return)}</b><small>RR {row.risk_reward || row.rrr || dash}</small></span>
                  <span>INR {formatPrice(row.entry_price ?? row.entry)}</span>
                  <span>INR {formatPrice(row.stop_loss ?? row.stoploss)}</span>
                  <span>INR {formatPrice(row.target1 ?? row.target_1)} / {formatPrice(row.target2 ?? row.target_2)}</span>
                  <span>{row.suggested_time || row.suggested_entry_time || dash}</span>
                  <span><b className={`signal-pill signal-pill--${signalOf(row).toLowerCase().replace(/\s+/g, '-')}`}>{signalOf(row)}</b></span>
                  {onMonitor && (
                    <span className="priority-row-actions" onClick={(event) => event.stopPropagation()}>
                      <button className="icon-button" type="button" title="Add to dashboard live monitor" onClick={() => onMonitor(row)}>
                        <BellPlus size={15} />
                      </button>
                    </span>
                  )}
                </button>
                {selected && (
                  <div className="selected-stock-detail selected-stock-detail--inline priority-selected-detail">
                    <div>
                      <span>Selected Stock</span>
                      <strong>{symbol}</strong>
                      <small>{row.source_name || row.priority_source || 'scanner'}</small>
                    </div>
                    <p>{reasonOf(row)}</p>
                    <div className="selected-stock-actions">
                      {onMonitor && <button className="btn-secondary" type="button" onClick={() => onMonitor(row)}><BellPlus size={15} /> Dashboard Monitor</button>}
                      <span className="status-badge status-good">Entry {formatPrice(row.entry_price ?? row.entry)}</span>
                      <span className="status-badge status-warn">SL {formatPrice(row.stop_loss ?? row.stoploss)}</span>
                      <span className="status-badge status-good">Target {formatPrice(row.target1 ?? row.target_1)}</span>
                      <button className="icon-button" type="button" title="Close details" onClick={() => setSelectedKey('')}><X size={15} /></button>
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
