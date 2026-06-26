"use client";
import React, { useEffect, useMemo, useState } from 'react';
import clsx from 'clsx';
import type { LucideIcon } from 'lucide-react';
import { Inbox, Search } from 'lucide-react';

export function PageHero({
  eyebrow,
  title,
  description,
  actions,
  metrics,
}: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: React.ReactNode;
  metrics?: Array<{ label: string; value: string; tone?: 'good' | 'bad' | 'warn' | 'info' }>;
}) {
  return (
    <section className="terminal-hero animate-in">
      <div className="terminal-hero__copy">
        <p className="terminal-eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="terminal-hero__right">
        {actions && <div className="terminal-actions">{actions}</div>}
        {metrics && (
          <div className="hero-metrics">
            {metrics.map((metric) => (
              <div key={metric.label} className="mini-metric">
                <span>{metric.label}</span>
                <strong className={metric.tone ? `tone-${metric.tone}` : undefined}>{metric.value}</strong>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

export function TerminalPanel({
  eyebrow,
  title,
  description,
  actions,
  children,
  className,
}: {
  eyebrow?: string;
  title?: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={clsx('terminal-panel animate-in', className)}>
      {(eyebrow || title || actions) && (
        <header className="terminal-panel__header">
          <div>
            {eyebrow && <p className="terminal-eyebrow">{eyebrow}</p>}
            {title && <h2>{title}</h2>}
            {description && <p>{description}</p>}
          </div>
          {actions && <div className="terminal-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function MetricTile({
  label,
  value,
  detail,
  icon: Icon,
  tone = 'neutral',
}: {
  label: string;
  value: string | number;
  detail?: string;
  icon?: LucideIcon;
  tone?: 'neutral' | 'good' | 'bad' | 'warn' | 'info';
}) {
  return (
    <div className={clsx('metric-tile', `metric-tile--${tone}`)}>
      <div className="metric-tile__icon">{Icon && <Icon size={18} />}</div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        {detail && <small>{detail}</small>}
      </div>
    </div>
  );
}

export function Toolbar({
  search,
  setSearch,
  tabs = [],
  activeTab,
  onTabChange,
  right,
}: {
  search?: string;
  setSearch?: (value: string) => void;
  tabs?: string[];
  activeTab?: string;
  onTabChange?: (tab: string) => void;
  right?: React.ReactNode;
}) {
  const [localSearch, setLocalSearch] = useState(search || '');

  useEffect(() => {
    setLocalSearch(search || '');
  }, [search]);

  useEffect(() => {
    if (!setSearch) return undefined;
    const timer = window.setTimeout(() => {
      setSearch(localSearch);
    }, 180);
    return () => window.clearTimeout(timer);
  }, [localSearch, setSearch]);

  return (
    <div className="terminal-toolbar">
      {setSearch && (
        <label className="terminal-search">
          <Search size={16} />
          <input value={localSearch} onChange={(event) => setLocalSearch(event.target.value)} placeholder="Search symbols, sectors, tags" />
        </label>
      )}
      {!!tabs.length && (
        <div className="segmented-control">
          {tabs.map((tab) => (
            <button key={tab} className={activeTab === tab ? 'active' : ''} onClick={() => onTabChange?.(tab)}>
              {tab}
            </button>
          ))}
        </div>
      )}
      <div className="terminal-toolbar__right">
        {right}
      </div>
    </div>
  );
}

export function DataTable({
  columns,
  rows,
  emptyTitle = 'No rows available',
  emptyBody = 'Run a scan or adjust filters to populate this table.',
}: {
  columns: string[];
  rows: Array<Array<React.ReactNode>>;
  emptyTitle?: string;
  emptyBody?: string;
}) {
  const visibleRows = useMemo(() => rows || [], [rows]);

  const getRowBackground = (row: React.ReactNode[]) => {
    const checkText = (node: any): string | null => {
      if (!node) return null;
      if (typeof node === 'string' || typeof node === 'number') {
        return String(node).toUpperCase();
      }
      if (Array.isArray(node)) {
        for (const item of node) {
          const res = checkText(item);
          if (res) return res;
        }
      }
      if (node.props) {
        if (node.props.children) {
          const res = checkText(node.props.children);
          if (res) return res;
        }
      }
      return null;
    };

    for (const cell of row) {
      const text = checkText(cell);
      if (text) {
        if (text === 'BUY' || text === 'TARGET HIT' || text.includes('BUY READY')) {
          return 'rgba(20, 184, 166, 0.05)';
        }
        if (text === 'SELL' || text === 'STOPLOSS HIT' || text.includes('SELL READY')) {
          return 'rgba(244, 63, 94, 0.05)';
        }
      }
    }
    return undefined;
  };

  return (
    <div className="table-wrap">
      {visibleRows.length ? (
        <table>
          <thead>
            <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
          </thead>
          <tbody>
            {visibleRows.map((row, rowIndex) => {
              const bg = getRowBackground(row);
              return (
                <tr key={rowIndex} style={bg ? { background: bg } : undefined}>
                  {row.map((cell, cellIndex) => <td key={cellIndex} data-label={columns[cellIndex]}>{cell}</td>)}
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <EmptyState title={emptyTitle} body={emptyBody} />
      )}
    </div>
  );
}

export function ProgressLine({ value, label }: { value: number; label?: string }) {
  return (
    <div className="progress-line">
      {label && <div className="progress-line__label"><span>{label}</span><strong>{value}%</strong></div>}
      <div className="progress-bar"><div className="progress-bar__fill" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></div>
    </div>
  );
}

export function EmptyState({ title = 'No data yet', body = 'Start a scan or wait for live events to populate this workspace.' }) {
  return (
    <div className="empty-state">
      <Inbox size={22} />
      <strong>{title}</strong>
      <span>{body}</span>
    </div>
  );
}
