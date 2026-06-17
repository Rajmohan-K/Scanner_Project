"use client";
import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useSelector } from 'react-redux';
import { Bell, Maximize2, Play, Save, Settings, Square, Sun } from 'lucide-react';
import CommandPalette from './CommandPalette';
import useDarkMode from '@/hooks/useDarkMode';
import { getV20Indices, saveV20Scanner, startScan, stopAllScans } from '@/lib/api';
import { useToast } from '@/components/layout/ToastProvider';
import { getActiveScanLabel, useActiveScanStatus } from '@/hooks/useActiveScanStatus';
import { RootState } from '@/state/store';

export default function TopMarketBar() {
  const { toggle } = useDarkMode();
  const toast = useToast();
  const savedSettings = useSelector((state: RootState) => state.settings.data);
  const [indices, setIndices] = useState<any[]>([]);
  const [loadingIndices, setLoadingIndices] = useState(true);
  const [scanToggling, setScanToggling] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState('');
  const indicesRef = React.useRef<any[]>([]);
  const { activeCount, primaryScan, refresh: refreshScanStatus } = useActiveScanStatus(1000);
  const scanRunning = activeCount > 0;
  const scanLabel = getActiveScanLabel(primaryScan);

  async function loadIndices(silent = false) {
    try {
      if (!silent || !indicesRef.current.length) setLoadingIndices(true);
      const payload = await getV20Indices();
      const next = Array.isArray(payload?.indices) ? payload.indices : [];
      indicesRef.current = next;
      setIndices(next);
      setLastRefreshed(new Date().toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true }));
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
    loadIndices();
    const timer = window.setInterval(() => loadIndices(true), 1000);
    return () => window.clearInterval(timer);
  }, []);

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

  async function handleSaveScan() {
    try {
      await saveV20Scanner('Live Dashboard Scanner', {
        min_expected_return_pct: 5,
        min_ml_probability: 62,
        min_risk_reward: 1.8,
        max_stop_distance_pct: 5,
      });
      toast?.push('Live scanner configuration saved', 'success');
    } catch {
      toast?.push('Unable to save scanner', 'error');
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
              <span>{item.name || item.symbol}</span>
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
            <span>Last refreshed</span>
            <strong>{lastRefreshed}</strong>
          </div>
        )}
      </div>
      <div className="top-actions">
        <Link className="icon-button" href="/notifications" title="Alerts and notifications" aria-label="Alerts and notifications"><Bell size={16} /></Link>
        <button className="icon-button" type="button" title="Toggle theme" onClick={toggle}><Sun size={16} /></button>
        <button className="icon-button" type="button" title="Fullscreen" onClick={handleFullscreen}><Maximize2 size={16} /></button>
        <button className="btn-secondary" type="button" onClick={handleSaveScan}><Save size={15} /> Save Scan</button>
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
