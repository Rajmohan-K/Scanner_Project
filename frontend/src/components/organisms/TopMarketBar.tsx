"use client";
import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useSelector } from 'react-redux';
import { Bell, Maximize2, Play, Settings, Square, Sun } from 'lucide-react';
import CommandPalette from './CommandPalette';
import useDarkMode from '@/hooks/useDarkMode';
import { ApiTargetMode, getApiTargetMode, getV20Indices, setApiTargetMode, startScan, stopAllScans } from '@/lib/api';
import { useToast } from '@/components/layout/ToastProvider';
import { getActiveScanLabel, useActiveScanStatus } from '@/hooks/useActiveScanStatus';
import { useRealtimeSnapshot } from '@/hooks/useRealtimeSnapshot';
import { useMarketStore } from '@/hooks/useMarketStore';
import { RootState } from '@/state/store';

function marketLabel(item: any) {
  const raw = `${item?.name || ''} ${item?.symbol || ''}`.toUpperCase();
  if (raw.includes('BSESN') || raw.includes('SENSEX')) return 'BSE';
  if (raw.includes('NSEI') || raw.includes('NIFTY 50') || raw.includes('NIFTY')) return 'NSE';
  if (raw.includes('BANK')) return 'BANK NIFTY';
  return item?.name || item?.symbol || 'INDEX';
}

export default function TopMarketBar() {
  const { toggle } = useDarkMode();
  const toast = useToast();
  const savedSettings = useSelector((state: RootState) => state.settings.data);
  const [indices, setIndices] = useState<any[]>([]);
  const [loadingIndices, setLoadingIndices] = useState(true);
  const [scanToggling, setScanToggling] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState('');
  const [apiTarget, setApiTarget] = useState<ApiTargetMode>('local');
  const indicesRef = React.useRef<any[]>([]);
  const { activeCount, primaryScan, refresh: refreshScanStatus } = useActiveScanStatus(2500);
  const connectionStatus = useMarketStore((state) => state.connectionStatus);
  const lastUpdated = useMarketStore((state) => state.lastUpdated);
  const realtime = useRealtimeSnapshot(1000);
  const scanRunning = activeCount > 0;
  const scanLabel = getActiveScanLabel(primaryScan);
  const realtimeAge = realtime.data?.freshness?.age_seconds;
  const realtimeStatus = realtime.error ? 'Offline' : realtime.stale ? 'Stale' : realtime.data?.status === 'empty' ? 'Empty' : 'Live';
  
  // V50 Provider status details
  const providerStatus = realtime.data?.provider_status;
  const providerName = providerStatus?.provider_name || 'yfinance';
  const providerState = providerStatus?.status || 'Connected';
  const successCount = providerStatus?.success_count || 0;
  const failureCount = providerStatus?.failure_count || 0;
  const errorReason = providerStatus?.error_reason || '';
  const isAutoMode = providerStatus?.is_auto_mode ?? true;

  const [countdown, setCountdown] = useState(10);
  const isConnected = connectionStatus === 'Connected' || connectionStatus === 'Stale Data';
  const connectionClass = connectionStatus.toLowerCase().replace(/\s+/g, '-');

  async function loadIndices(silent = false) {
    try {
      if (!silent || !indicesRef.current.length) setLoadingIndices(true);
      const payload = await getV20Indices();
      const next = Array.isArray(payload?.indices) ? payload.indices : [];
      indicesRef.current = next;
      setIndices(next);
      
      let latestTime = '';
      if (next.length > 0) {
        const timestamps = next
          .map((item: any) => item.updated_at)
          .filter(Boolean);
        if (timestamps.length > 0) {
          const maxTs = timestamps.reduce((max: string, current: string) => current > max ? current : max, timestamps[0]);
          try {
            const dateObj = new Date(maxTs);
            if (!isNaN(dateObj.getTime())) {
              latestTime = dateObj.toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true });
            }
          } catch (e) {
            // ignore
          }
        }
      }
      if (!latestTime) {
        latestTime = new Date().toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true });
      }
      setLastRefreshed(latestTime);
      setCountdown(10);
    } catch {
      if (!silent) {
        setIndices([]);
        indicesRef.current = [];
        toast?.push('Market index feed unavailable', 'error');
      }
    } finally {
      if (!silent || !indicesRef.current.length) setLoadingIndices(false);
    }
  }

  useEffect(() => {
    setApiTarget(getApiTargetMode());
    loadIndices();
  }, []);

  useEffect(() => {
    const countdownTimer = window.setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          loadIndices(true);
          return 10;
        }
        return prev - 1;
      });
    }, 1000);
    return () => window.clearInterval(countdownTimer);
  }, []);

  function handleApiTargetChange(mode: ApiTargetMode) {
    setApiTarget(mode);
    setApiTargetMode(mode);
    setIndices([]);
    indicesRef.current = [];
    setLoadingIndices(true);
    toast?.push(`API target changed to ${mode === 'server' ? 'Server' : 'Local'}`, 'success');
    window.setTimeout(() => loadIndices(), 50);
  }

  async function handleScanToggle() {
    try {
      setScanToggling(true);
      if (scanRunning) {
        await stopAllScans();
        toast?.push('Active scan stopped', 'success');
      } else {
        const result = await startScan({
          scan_mode: 'v20-dashboard',
          auto_nse_universe: true,
          period: '6mo',
          interval: '1d',
          top_n: 20,
          candidate_pool: Number(savedSettings.custom_candidate_pool || 97),
          validation_pool: Number(savedSettings.custom_validation_pool || 35),
          strict_shortlist: true,
          min_expected_return_pct: 5,
          min_ml_probability: Number(savedSettings.ml_threshold || 62),
          min_risk_reward: Number(savedSettings.swing_min_rr || 1.8),
          max_stop_distance_pct: 5,
          min_data_reliability_score: 35,
          min_profitability_score: 18,
        });
        toast?.push(`Live V20 scan started: ${result.scan_id}`, 'success');
      }
      await refreshScanStatus();
    } catch {
      toast?.push(scanRunning ? 'Unable to stop active scan' : 'Unable to start live V20 scan', 'error');
    } finally {
      setScanToggling(false);
    }
  }

  async function handleFullscreen() {
    try {
      if (!document.fullscreenElement) await document.documentElement.requestFullscreen();
      else await document.exitFullscreen();
    } catch {
      toast?.push('Fullscreen is unavailable in this browser', 'warning');
    }
  }

  return (
    <div className="top-market-bar">
      <div className="top-search-zone">
        <CommandPalette />
      </div>
      <div className="top-ticker-strip">
        {loadingIndices ? Array.from({ length: 2 }).map((_, index) => (
          <div className="top-ticker skeleton-line" key={`index-loading-${index}`}>
            <span>Loading</span>
            <strong>--</strong>
            <em>--</em>
          </div>
        )) : indices.length ? indices.slice(0, 4).map((item) => {
          const change = Number(item.change_pct || 0);
            return (
              <div className="top-ticker" key={item.symbol || item.name}>
              <span>{marketLabel(item)}</span>
              <strong>{Number(item.value || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}</strong>
              <em className={change >= 0 ? 'positive' : 'negative'}>{change >= 0 ? '+' : ''}{change.toFixed(2)}%</em>
            </div>
          );
        }) : (
          <div className="top-ticker">
            <span>Market Feed</span>
            <strong>Unavailable</strong>
            <em className="negative">Configure provider</em>
          </div>
        )}
        {lastRefreshed && (
          <div className="last-refresh-chip">
            <span>Last Tick</span>
            <strong>{lastRefreshed}</strong>
          </div>
        )}
        <div className={`realtime-health-chip ${isConnected ? 'live' : 'offline'}`} style={{ marginRight: '8px', display: 'flex', alignItems: 'center' }}>
          <span style={{ display: 'flex', alignItems: 'center' }}>
            {isConnected && (
              <span className="live-pulse-dot" style={{
                display: 'inline-block',
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                backgroundColor: '#10B981',
                marginRight: '6px',
                boxShadow: '0 0 8px #10B981'
              }}></span>
            )}
            Backend
          </span>
          <strong>{connectionStatus}</strong>
        </div>
        <div className={`realtime-health-chip ${providerState === 'Failed' ? 'offline' : (realtimeStatus.toLowerCase() === 'stale' ? 'stale' : 'live')}`} style={{ marginRight: '8px' }} title={errorReason ? `Provider Error: ${errorReason}` : `Success count: ${successCount} / Fails: ${failureCount}`}>
          <span>Market Feed</span>
          <strong>{providerState === 'Failed' ? 'Failed' : (realtimeStatus === 'Stale' ? 'Stale' : 'Live')}</strong>
        </div>
        <div className="realtime-health-chip top-status-next live" style={{ marginRight: '8px' }} title={`Next cycle scans ${isAutoMode ? 'automatically' : 'manually'}`}>
          <span>Next Scan</span>
          <strong>{countdown}s {isAutoMode ? '(Auto)' : '(Manual)'}</strong>
        </div>
        <div className="realtime-health-chip top-status-provider live" style={{ marginRight: '8px' }}>
          <span>Provider</span>
          <strong>{providerName.toUpperCase()}</strong>
        </div>
        {realtimeAge !== undefined && (
          <div className={`realtime-health-chip top-status-age ${realtime.stale ? 'offline' : 'live'}`} style={{ marginRight: '8px' }}>
            <span>Data Age</span>
            <strong>{realtimeAge}s</strong>
          </div>
        )}
        {realtime.stale && (
          <div className="realtime-health-chip offline" style={{ marginRight: '8px' }}>
            <span>Warning</span>
            <strong>STALE ROW WARNING</strong>
          </div>
        )}
      </div>
      <div className="top-actions">
        <span
          className={`live-conn-pill top-live-feed-pill live-conn-pill--${connectionClass}`}
          title={lastUpdated ? `Last update: ${lastUpdated}` : 'Connecting to live feed...'}
        >
          <span className="live-conn-dot" />
          {connectionStatus}
        </span>
        <Link className="icon-button" href="/notifications" title="Alerts and notifications" aria-label="Alerts and notifications"><Bell size={16} /></Link>
        <button className="icon-button" type="button" title="Toggle theme" onClick={toggle}><Sun size={16} /></button>
        <button className="icon-button" type="button" title="Fullscreen" onClick={handleFullscreen}><Maximize2 size={16} /></button>
        <select className="api-target-select" value={apiTarget} onChange={(event) => handleApiTargetChange(event.target.value as ApiTargetMode)} title="Backend API target">
          <option value="local">Local API</option>
          <option value="server">Server API</option>
        </select>
        {scanRunning && <span className="top-scan-chip" title={scanLabel}>{activeCount} active</span>}
        <button
          className={scanRunning ? 'btn-danger' : 'btn-primary'}
          type="button"
          onClick={handleScanToggle}
          disabled={scanToggling}
          title={scanRunning ? `Stop ${scanLabel}` : 'Run live scan'}
        >
          {scanRunning ? <Square size={15} /> : <Play size={15} />}
          {scanToggling ? 'Working...' : scanRunning ? 'Stop Scan' : 'Run Scan'}
        </button>
        <Link className="icon-button" href="/settings" title="Settings"><Settings size={16} /></Link>
        <span className="user-avatar">R</span>
      </div>
    </div>
  );
}
