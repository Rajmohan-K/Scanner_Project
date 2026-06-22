"use client";

import React, { useEffect, useRef } from 'react';
import { getWatchlistHistory, getWatchlistStreamUrl, type AlertHistoryRecord } from '@/lib/api';
import {
  markAlertSeen,
  notifyWatchlistAlert,
  readSeenAlertIds,
  readWatchlistAlertSettings,
  storeWatchlistAlertSettings,
  WATCHLIST_ALERT_SETTINGS_KEY,
} from '@/lib/watchlistAlerts';
import { useToast } from '@/components/layout/ToastProvider';

const MISSED_ALERT_WINDOW_MS = 15 * 60 * 1000;

function parseAlertPayload(raw: string): AlertHistoryRecord | null {
  try {
    const payload = JSON.parse(raw);
    return payload?.alert || null;
  } catch {
    return null;
  }
}

function isRecentAlert(alert: AlertHistoryRecord) {
  if (!alert.created_at) return false;
  const created = new Date(alert.created_at).getTime();
  return Number.isFinite(created) && Date.now() - created <= MISSED_ALERT_WINDOW_MS;
}

export function WatchlistAlertListener() {
  const toast = useToast();
  const bootstrapped = useRef(false);

  useEffect(() => {
    const settings = readWatchlistAlertSettings();
    if (
      settings.desktop_enabled !== false 
      && typeof window !== 'undefined' 
      && 'Notification' in window 
      && window.Notification.permission === 'default'
    ) {
      window.Notification.requestPermission().catch(() => {});
    }
  }, []);

  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;

    async function notifyMissedAlerts() {
      try {
        const response = await getWatchlistHistory({ limit: 20 });
        const alerts = response.alerts || [];
        const seen = readSeenAlertIds();
        const settings = readWatchlistAlertSettings();
        let notified = 0;
        alerts.forEach((alert) => {
          if (!alert.alert_id || seen.has(alert.alert_id)) return;
          if (isRecentAlert(alert) && notified < 5) {
            if (notifyWatchlistAlert(alert, settings, toast)) notified += 1;
            return;
          }
          markAlertSeen(alert.alert_id);
        });
      } catch {
        // Backend may be offline during startup.
      }
    }

    notifyMissedAlerts();
  }, [toast]);

  useEffect(() => {
    function syncSettings() {
      try {
        const stored = window.localStorage.getItem(WATCHLIST_ALERT_SETTINGS_KEY);
        if (stored) storeWatchlistAlertSettings(JSON.parse(stored));
      } catch {
        // Ignore malformed local settings.
      }
    }

    syncSettings();
    window.addEventListener('storage', syncSettings);
    return () => window.removeEventListener('storage', syncSettings);
  }, []);

  useEffect(() => {
    const source = new EventSource(getWatchlistStreamUrl());

    source.addEventListener('WATCHLIST_ALERT', (event) => {
      const alert = parseAlertPayload((event as MessageEvent).data);
      if (!alert) return;
      notifyWatchlistAlert(alert, readWatchlistAlertSettings(), toast);
    });

    source.addEventListener('WATCHLIST_UPDATED', (event) => {
      try {
        const payload = JSON.parse((event as MessageEvent).data);
        const alerts: AlertHistoryRecord[] = payload.alerts || [];
        const settings = readWatchlistAlertSettings();
        const seen = readSeenAlertIds();
        alerts
          .filter((alert) => alert.alert_id && !seen.has(alert.alert_id))
          .slice(0, 3)
          .forEach((alert) => notifyWatchlistAlert(alert, settings, toast));
      } catch {
        // Ignore malformed stream payloads.
      }
    });

    return () => source.close();
  }, [toast]);

  return null;
}

export default WatchlistAlertListener;
