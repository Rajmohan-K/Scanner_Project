"use client";
import React, { useEffect, useMemo, useState } from 'react';
import { getActiveScan, getHealth, getMarketWidgets, getScanSummaries } from '@/lib/api';
import { useRealtime } from '@/hooks/useRealtime';

function marketStatus(now: Date) {
  const minutes = now.getHours() * 60 + now.getMinutes();
  if (minutes < 9 * 60) return 'Pre Market';
  if (minutes >= 9 * 60 && minutes < 15 * 60 + 30) return 'Market Open';
  if (minutes >= 15 * 60 + 30 && minutes < 17 * 60) return 'Post Market';
  return 'Market Closed';
}

function displayValue(value: unknown, fallback: string) {
  if (value === null || value === undefined || value === '') return fallback;
  if (typeof value === 'number') {
    return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(value);
  }
  return String(value);
}

function titleize(value: unknown) {
  return String(value || '')
    .replace(/[-_]/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function readableScanName(scan: any) {
  return titleize(scan?.scan_type || scan?.scanMode || scan?.scan_mode || scan?.type || scan?.display_name || '');
}

function toneClass(value: string, type: 'market' | 'api' | 'feed' | 'progress' | 'scan' = 'api') {
  const normalized = value.toLowerCase();
  if (type === 'market') {
    if (normalized.includes('open')) return 'status-good';
    if (normalized.includes('post') || normalized.includes('pre')) return 'status-warn';
    return 'status-bad';
  }
  if (type === 'scan') {
    if (normalized.includes('running')) return 'status-good';
    if (normalized.includes('paused') || normalized.includes('queued')) return 'status-warn';
    if (normalized.includes('error') || normalized.includes('cancel')) return 'status-bad';
    if (normalized.includes('complete')) return 'status-good';
    return 'status-warn';
  }
  if (type === 'progress') {
    return value === '100%' || normalized.includes('running') ? 'status-good' : 'status-warn';
  }
  if (normalized.includes('online') || normalized.includes('available') || normalized.includes('ok')) return 'status-good';
  if (normalized.includes('offline') || normalized.includes('error') || normalized.includes('failed')) return 'status-bad';
  return 'status-warn';
}

export function MarketWidgetStrip() {
  const [mounted, setMounted] = useState(false);
  const [now, setNow] = useState<Date | null>(null);
  const [live, setLive] = useState<Record<string, any>>({});
  const liveStatusInFlightRef = React.useRef(false);
  const liveStatusFailuresRef = React.useRef(0);

  useEffect(() => {
    setMounted(true);
    setNow(new Date());
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    async function loadLiveStatus() {
      if (liveStatusInFlightRef.current) return;
      liveStatusInFlightRef.current = true;
      try {
        const [healthResult, scansResult, marketResult, activeScanResult] = await Promise.allSettled([
          getHealth(),
          getScanSummaries(),
          getMarketWidgets(),
          getActiveScan(),
        ]);
        const failedCount = [healthResult, scansResult, marketResult, activeScanResult]
          .filter((result) => result.status === 'rejected').length;
        if (failedCount === 4) {
          liveStatusFailuresRef.current += 1;
          if (liveStatusFailuresRef.current >= 3) {
            setLive((current) => ({ ...current, api: 'Offline', feed: current.feed || 'Unavailable' }));
          }
          return;
        }
        liveStatusFailuresRef.current = 0;
        const health = healthResult.status === 'fulfilled' ? healthResult.value : null;
        const scans = scansResult.status === 'fulfilled' ? scansResult.value : [];
        const market = marketResult.status === 'fulfilled' ? marketResult.value : {};
        const activeScan = activeScanResult.status === 'fulfilled' ? activeScanResult.value : null;
        const latestScan = scans?.[0];
        const latestMessage = latestScan?.message || health?.latest_scan?.message;
        const scanName = activeScan?.display_name || activeScan?.scan_type || market?.scanType || readableScanName(latestScan);
        const scanStatus = titleize(activeScan?.status || market?.scanStatus || (latestScan ? 'completed' : 'idle'));
        setLive((current) => ({
          ...current,
          ...market,
          system: health?.status || health?.system_status,
          api: health || activeScan || marketResult.status === 'fulfilled' || scansResult.status === 'fulfilled' ? 'Online' : current.api || 'Checking',
          feed: health?.data_feed_status || health?.feed_status || (latestScan ? 'Scan data available' : undefined),
          currentScan: scanName || 'No scan yet',
          scanStatus,
          progress: activeScan?.progress || market?.progress || (typeof latestScan?.progress === 'number' ? `${latestScan.progress}%` : latestScan ? '100%' : undefined),
          lastScan: market?.lastScan || latestScan?.completed_at || latestScan?.updated_at || latestScan?.created_at,
          lastAnalysis: market?.lastAnalysis || latestScan?.last_analysis_time || latestScan?.analysis_completed_at || latestMessage,
          breadth: market?.breadth || latestScan?.market_breadth,
        }));
      } catch {
        liveStatusFailuresRef.current += 1;
        if (liveStatusFailuresRef.current >= 3) {
          setLive((current) => ({ ...current, api: 'Offline' }));
        }
      } finally {
        liveStatusInFlightRef.current = false;
      }
    }
    loadLiveStatus();
    const timer = window.setInterval(loadLiveStatus, 3000);
    return () => window.clearInterval(timer);
  }, []);

  useRealtime((msg) => {
    if (!msg?.payload) return;
    if (msg.type === 'market.tick' || msg.type === 'market-status' || msg.type === 'system-status' || msg.type === 'scan.update') {
      setLive((current) => ({ ...current, ...msg.payload }));
    }
  });

  const status = useMemo(() => {
    const time = mounted && now
      ? new Intl.DateTimeFormat('en-IN', {
          timeZone: 'Asia/Kolkata',
          hour: 'numeric',
          minute: '2-digit',
          second: '2-digit',
          hour12: true,
        }).format(now)
      : 'Loading...';

    return {
      time,
      market: now ? marketStatus(now) : 'Loading...',
      nse: displayValue(live.nse || live.nse_index, 'Unavailable'),
      sensex: displayValue(live.sensex, 'Unavailable'),
      bankNifty: displayValue(live.bank_nifty || live.banknifty, 'Unavailable'),
      nifty50: displayValue(live.nifty50 || live.nifty_50, 'Unavailable'),
      currentScan: displayValue(live.currentScan, 'No scan yet'),
      scanStatus: displayValue(live.scanStatus, 'Idle'),
      progress: displayValue(live.progress, 'Unavailable'),
      breadth: displayValue(live.breadth, 'No completed scan'),
      health: displayValue(live.system, 'Checking'),
      api: displayValue(live.api, 'Checking'),
      feed: displayValue(live.feed, 'Checking'),
    };
  }, [live, mounted, now]);

  return (
    <div className="market-widget-strip market-widget-strip--compact" aria-label="Pinned market widgets">
      <div className="market-status-chip">
        <strong suppressHydrationWarning>{status.time}</strong>
        <span className={toneClass(status.market, 'market')}>{status.market}</span>
      </div>
      <div className="market-ticker-row">
        <span>NSE <strong>{status.nse}</strong></span>
        <span>Sensex <strong>{status.sensex}</strong></span>
        <span>Bank Nifty <strong>{status.bankNifty}</strong></span>
        <span>Nifty 50 <strong>{status.nifty50}</strong></span>
      </div>
      <div className="market-scan-row">
        <span>Scan <strong>{status.currentScan}</strong></span>
        <span className={toneClass(status.scanStatus, 'scan')}>{status.scanStatus}</span>
        <span className={toneClass(status.progress, 'progress')}>{status.progress}</span>
        <span>{status.breadth}</span>
        <span>API <strong className={toneClass(status.api)}>{status.api}</strong></span>
        <span>Feed <strong className={toneClass(status.feed, 'feed')}>{status.feed}</strong></span>
      </div>
    </div>
  );
}

export default MarketWidgetStrip;
