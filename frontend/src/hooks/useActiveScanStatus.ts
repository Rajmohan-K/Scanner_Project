"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getActiveScans, getOptimisticActiveScans, SCAN_STATUS_EVENT } from '@/lib/api';

export type ActiveScan = {
  scan_id?: string;
  id?: string;
  status?: string;
  scan_mode?: string;
  scan_type?: string;
  type?: string;
  display_name?: string;
  progress?: number;
  current_symbol?: string;
  started_at?: string;
  [key: string]: unknown;
};

function extractActiveScans(payload: any): ActiveScan[] {
  const scans = payload?.active_scans || payload?.scans || payload?.active || [];
  if (!Array.isArray(scans)) return [];
  return scans.filter((scan) => {
    const status = String(scan?.status || 'running').toLowerCase();
    return !['completed', 'cancelled', 'canceled', 'error', 'stopped'].includes(status);
  });
}

function withTimeout<T>(promise: Promise<T>, timeoutMs = 3500): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error('Scan status timed out')), timeoutMs);
    promise
      .then((value) => {
        window.clearTimeout(timer);
        resolve(value);
      })
      .catch((err) => {
        window.clearTimeout(timer);
        reject(err);
      });
  });
}

function mergeActiveScans(serverScans: ActiveScan[], optimisticScans: ActiveScan[]) {
  const merged = [...serverScans];
  const serverIds = new Set(serverScans.map((scan) => String(scan.scan_id || scan.id || '')));
  optimisticScans.forEach((scan) => {
    const scanId = String(scan.scan_id || scan.id || '');
    if (scanId && !serverIds.has(scanId)) merged.unshift(scan);
  });
  return merged;
}

export function getActiveScanLabel(scan?: ActiveScan) {
  if (!scan) return 'No active scan';
  const raw = scan.display_name || scan.scan_mode || scan.scan_type || scan.type || 'Live Scan';
  return String(raw)
    .replace(/^v20[-_\s]*/i, 'V20 ')
    .replace(/[-_]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function useActiveScanStatus(pollMs = 5000) {
  const [activeScans, setActiveScans] = useState<ActiveScan[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const inFlightRef = useRef(false);
  const failuresRef = useRef(0);

  const refresh = useCallback(async () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    setLoading(true);
    try {
      const payload = await withTimeout(getActiveScans());
      failuresRef.current = 0;
      setActiveScans(mergeActiveScans(extractActiveScans(payload), getOptimisticActiveScans()));
      setError('');
    } catch {
      failuresRef.current += 1;
      const optimistic = getOptimisticActiveScans();
      setActiveScans((current) => (current.length ? mergeActiveScans(current, optimistic) : optimistic));
      setError(failuresRef.current >= 3 ? 'Scan status unavailable' : '');
    } finally {
      inFlightRef.current = false;
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      if (!cancelled) await refresh();
    };
    load();
    const timer = window.setInterval(load, pollMs);
    const handleOptimisticStatus = () => setActiveScans((current) => mergeActiveScans(current, getOptimisticActiveScans()));
    window.addEventListener(SCAN_STATUS_EVENT, handleOptimisticStatus);
    window.addEventListener('storage', handleOptimisticStatus);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      window.removeEventListener(SCAN_STATUS_EVENT, handleOptimisticStatus);
      window.removeEventListener('storage', handleOptimisticStatus);
    };
  }, [pollMs, refresh]);

  return useMemo(() => ({
    activeScans,
    activeCount: activeScans.length,
    primaryScan: activeScans[0],
    loading,
    error,
    refresh,
  }), [activeScans, error, loading, refresh]);
}
