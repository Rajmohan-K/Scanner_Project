"use client";

import { useCallback, useEffect, useMemo, useState } from 'react';
import useSWR from 'swr';
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
  const { data, error, isLoading, mutate } = useSWR('/api/scan/active/all', () => getActiveScans(), {
    refreshInterval: pollMs,
    dedupingInterval: 2000,
    errorRetryCount: 3,
  });

  const [optimistic, setOptimistic] = useState<ActiveScan[]>(() => getOptimisticActiveScans());

  useEffect(() => {
    const handleOptimisticStatus = () => {
      setOptimistic(getOptimisticActiveScans());
    };
    window.addEventListener(SCAN_STATUS_EVENT, handleOptimisticStatus);
    window.addEventListener('storage', handleOptimisticStatus);
    return () => {
      window.removeEventListener(SCAN_STATUS_EVENT, handleOptimisticStatus);
      window.removeEventListener('storage', handleOptimisticStatus);
    };
  }, []);

  const activeScans = useMemo(() => {
    return mergeActiveScans(extractActiveScans(data), optimistic);
  }, [data, optimistic]);

  const refresh = useCallback(async () => {
    await mutate();
  }, [mutate]);

  return useMemo(() => ({
    activeScans,
    activeCount: activeScans.length,
    primaryScan: activeScans[0],
    loading: isLoading,
    error: error ? 'Scan status unavailable' : '',
    refresh,
  }), [activeScans, error, isLoading, refresh]);
}
