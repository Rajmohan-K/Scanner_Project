"use client";

import { useCallback, useEffect, useMemo, useState } from 'react';
import { getActiveScans } from '@/lib/api';

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

  const refresh = useCallback(async () => {
    try {
      const payload = await withTimeout(getActiveScans());
      setActiveScans(extractActiveScans(payload));
      setError('');
    } catch {
      setActiveScans([]);
      setError('Scan status unavailable');
    } finally {
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
    return () => {
      cancelled = true;
      window.clearInterval(timer);
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
