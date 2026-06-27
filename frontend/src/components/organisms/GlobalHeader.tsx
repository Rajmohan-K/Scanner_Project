"use client";
import React, { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Activity, Bot, FileText, LayoutDashboard, LineChart, Radar, ShieldCheck, Star, Target, Trophy, UploadCloud } from 'lucide-react';
import { getActiveScanLabel, useActiveScanStatus } from '@/hooks/useActiveScanStatus';
import { useRealtime } from '@/hooks/useRealtime';
import { addPriorityCandidates, inferPriorityHorizon } from '@/lib/priorityPicks';

const navItems = [
  ['Watchlist Monitor', '/watchlist', Star],
  ['ALGO Watchlist', '/algo-watchlist', Target],
  ['Signal History', '/signals', Target],
  ['Dashboard', '/dashboard', LayoutDashboard],
  ['Algo Trading', '/algo-trading', Bot],
  ['Stock Scanner', '/scan-center', Radar],
  ['Priority Picks', '/priority-picks', Trophy],
  ['Groww Source', '/groww-intraday', UploadCloud],
  ['Intelligence Center', '/ai-insights', Target],
  ['Reports', '/reports', FileText],
] as const;

function getIstMarketStatus(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Kolkata',
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).formatToParts(now);
  const value = (type: string) => parts.find((part) => part.type === type)?.value || '';
  const weekday = value('weekday');
  const hour = Number(value('hour'));
  const minute = Number(value('minute'));
  const total = hour * 60 + minute;
  const isWeekend = weekday === 'Sat' || weekday === 'Sun';
  let label = 'Closed';
  let tone = 'closed';
  if (!isWeekend && total >= 9 * 60 && total < 9 * 60 + 15) {
    label = 'Pre-market';
    tone = 'premarket';
  } else if (!isWeekend && total >= 9 * 60 + 15 && total < 15 * 60 + 30) {
    label = 'Open';
    tone = 'open';
  } else if (!isWeekend && total >= 15 * 60 + 30 && total < 16 * 60) {
    label = 'Post-market';
    tone = 'postmarket';
  }
  const displayTime = new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  }).format(now);
  return { label, tone, displayTime };
}

export function GlobalHeader() {
  const pathname = usePathname();
  const { activeCount, primaryScan, loading, error } = useActiveScanStatus(2500);

  useRealtime((msg) => {
    if (msg?.type === 'push-to-priority-picks' && Array.isArray(msg.payload)) {
      const intradayCandidates: any[] = [];
      const swingCandidates: any[] = [];
      msg.payload.forEach((candidate: any) => {
        const horizon = candidate.horizon || candidate.priority_horizon || inferPriorityHorizon(candidate);
        if (horizon === 'swing') {
          swingCandidates.push(candidate);
        } else {
          intradayCandidates.push(candidate);
        }
      });
      if (intradayCandidates.length > 0) {
        addPriorityCandidates(intradayCandidates, 'intraday');
      }
      if (swingCandidates.length > 0) {
        addPriorityCandidates(swingCandidates, 'swing');
      }
    }
  });

  const scanStatus = String(primaryScan?.status || (activeCount ? 'running' : 'idle')).toLowerCase();
  const scanLabel = getActiveScanLabel(primaryScan);
  const scanStatusText = loading
    ? 'Syncing with backend'
    : error || (activeCount ? `${scanStatus} / ${activeCount} active` : 'Ready for next scan');
  const [mounted, setMounted] = useState(false);
  const [clock, setClock] = useState(() => ({ label: 'Market', tone: 'closed', displayTime: '--:--:--' }));
  const marketTitle = useMemo(() => `${clock.label} / IST ${clock.displayTime}`, [clock]);

  useEffect(() => {
    setMounted(true);
    setClock(getIstMarketStatus());
    const timer = window.setInterval(() => setClock(getIstMarketStatus()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <header className="global-header">
      <div className="sidebar-brand-row">
        <Link href="/watchlist" className="brand">
          <span className="brand-orb">V50</span>
          <strong>Scanner</strong>
          <em className={`market-status market-status--${clock.tone}`} title={marketTitle} suppressHydrationWarning>
            {mounted ? clock.label : 'Market'} <small suppressHydrationWarning>{mounted ? clock.displayTime : '--:--:--'}</small>
          </em>
        </Link>
      </div>
      <nav className="global-nav" aria-label="Primary navigation">
        {navItems.map(([label, href, Icon]) => (
          <Link key={`${label}-${href}`} href={href} title={label} aria-label={label} className={pathname === href ? 'active' : ''}>
            <Icon size={17} />
            <span>{label}</span>
            {label === 'Stock Scanner' && <b className="nav-badge">LIVE</b>}
          </Link>
        ))}
      </nav>
      <div className={`sidebar-scan-status ${activeCount ? 'is-running' : ''}`}>
        <span>Live Scan Status</span>
        <strong>{loading ? 'Checking scan status...' : scanLabel}</strong>
        <small>{scanStatusText}</small>
        <Link href="/scan-center">{activeCount ? 'View / Stop Scan' : 'Open Scan Center'}</Link>
      </div>
    </header>
  );
}

export default GlobalHeader;
