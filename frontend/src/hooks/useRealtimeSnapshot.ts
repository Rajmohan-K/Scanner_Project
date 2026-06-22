"use client";

import { useCallback, useEffect, useRef, useState } from 'react';
import { getRealtimeSnapshot } from '@/lib/api';

export type RealtimeSnapshotState = {
  data: any | null;
  loading: boolean;
  error: string;
  connected: boolean;
  stale: boolean;
  lastUpdated: string;
  refresh: () => Promise<void>;
};

export function useRealtimeSnapshot(intervalMs = 1000): RealtimeSnapshotState {
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const mountedRef = useRef(true);
  const inFlightRef = useRef(false);
  const failuresRef = useRef(0);

  const load = useCallback(async () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    try {
      const payload = await getRealtimeSnapshot();
      if (!mountedRef.current) return;
      setData(payload);
      failuresRef.current = 0;
      setError('');
    } catch (err: any) {
      if (!mountedRef.current) return;
      failuresRef.current += 1;
      if (failuresRef.current >= 3) {
        setError(err?.response?.data?.message || err?.message || 'Realtime snapshot unavailable');
      }
    } finally {
      inFlightRef.current = false;
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    load();
    const timer = window.setInterval(load, intervalMs);
    return () => {
      mountedRef.current = false;
      window.clearInterval(timer);
    };
  }, [intervalMs, load]);

  const stale = Boolean(data?.freshness?.stale);
  return {
    data,
    loading,
    error,
    connected: Boolean(data && !error),
    stale,
    lastUpdated: String(data?.freshness?.updated_at || data?.generated_at || ''),
    refresh: load,
  };
}
