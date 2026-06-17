"use client";
import React, { useEffect, useRef, useState } from 'react';
import { readGrowwSettings, runGrowwIntradayAnalysis, writeGrowwSettings, GROWW_EVENT } from '@/lib/growwIntraday';
import { useToast } from '@/components/layout/ToastProvider';

export function GrowwAutoScanner() {
  const toast = useToast();
  const [settings, setSettings] = useState(readGrowwSettings);
  const runningRef = useRef(false);
  const lastRunRef = useRef(0);

  useEffect(() => {
    function sync() {
      setSettings(readGrowwSettings());
    }
    sync();
    window.addEventListener(GROWW_EVENT, sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener(GROWW_EVENT, sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  useEffect(() => {
    if (!settings.enabled) return;

    async function tick(force = false) {
      const intervalMs = Math.max(1, Number(settings.intervalMinutes || 15)) * 60 * 1000;
      if (runningRef.current) return;
      if (!force && Date.now() - lastRunRef.current < intervalMs) return;
      runningRef.current = true;
      lastRunRef.current = Date.now();
      try {
        const result = await runGrowwIntradayAnalysis(settings.limit);
        toast.push(`Auto Groww scan updated ${result.rows.length} filtered stocks`, 'success', { dedupeKey: 'groww-auto-success' });
      } catch (error: any) {
        toast.push(error?.message || 'Auto Groww scan failed', 'error', { dedupeKey: 'groww-auto-error' });
      } finally {
        runningRef.current = false;
      }
    }

    tick(true);
    const timer = window.setInterval(() => tick(false), 30000);
    return () => window.clearInterval(timer);
  }, [settings.enabled, settings.intervalMinutes, settings.limit, toast]);

  useEffect(() => {
    if (!window.localStorage.getItem('groww-intraday-auto-settings')) {
      writeGrowwSettings(settings);
    }
  }, [settings]);

  return null;
}

export default GrowwAutoScanner;
