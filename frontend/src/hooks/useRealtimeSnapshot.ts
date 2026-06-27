"use client";

import { useCallback } from 'react';
import useSWR from 'swr';
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
  const { data, error, isLoading, mutate } = useSWR('/api/realtime/snapshot', () => getRealtimeSnapshot(), {
    refreshInterval: intervalMs,
    dedupingInterval: 2000,
    errorRetryCount: 3,
  });

  const refresh = useCallback(async () => {
    await mutate();
  }, [mutate]);

  const stale = Boolean(data?.freshness?.stale);
  return {
    data: data || null,
    loading: isLoading,
    error: error ? 'Realtime snapshot unavailable' : '',
    connected: Boolean(data && !error),
    stale,
    lastUpdated: String(data?.freshness?.updated_at || data?.generated_at || ''),
    refresh,
  };
}
