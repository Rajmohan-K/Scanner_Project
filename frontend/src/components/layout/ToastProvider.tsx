"use client";
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

export type ToastType = 'info'|'success'|'error'|'warning';
export type NotificationRecord = {
  id: string;
  type: ToastType;
  message: string;
  createdAt: string;
  updatedAt: string;
  count: number;
};

type Toast = { id: string; type?: ToastType; message: string; count?: number };
type PushOptions = { dedupeKey?: string; desktop?: boolean; persist?: boolean };

const HISTORY_KEY = 'scanner-notification-history';
const DESKTOP_KEY = 'scanner-desktop-alerts-enabled';
const HISTORY_EVENT = 'scanner-notifications-updated';
const DEDUPE_MS = 30000;

const ToastCtx = createContext<{
  push: (message: string, type?: ToastType, options?: PushOptions) => void;
  desktopEnabled: boolean;
  setDesktopEnabled: (enabled: boolean) => Promise<void>;
  requestDesktopPermission: () => Promise<NotificationPermission | 'unsupported'>;
} | null>(null);

export function readNotificationHistory(): NotificationRecord[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(HISTORY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function clearNotificationHistory() {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(HISTORY_KEY);
  window.dispatchEvent(new Event(HISTORY_EVENT));
}

function saveNotificationHistory(history: NotificationRecord[]) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, 200)));
  window.dispatchEvent(new Event(HISTORY_EVENT));
}

function appendNotification(message: string, type: ToastType, dedupeKey: string) {
  const now = new Date().toISOString();
  const history = readNotificationHistory();
  const existingIndex = history.findIndex((item) => `${item.type}:${item.message}` === dedupeKey);
  if (existingIndex >= 0) {
    const existing = history[existingIndex];
    history.splice(existingIndex, 1);
    saveNotificationHistory([{ ...existing, updatedAt: now, count: existing.count + 1 }, ...history]);
    return existing.count + 1;
  }
  saveNotificationHistory([{ id: `${Date.now()}${Math.random().toString(36).slice(2, 7)}`, type, message, createdAt: now, updatedAt: now, count: 1 }, ...history]);
  return 1;
}

export function useToast() {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [list, setList] = useState<Toast[]>([]);
  const [desktopEnabledState, setDesktopEnabledState] = useState(false);
  const recentRef = useRef(new Map<string, number>());

  useEffect(() => {
    try {
      setDesktopEnabledState(window.localStorage.getItem(DESKTOP_KEY) === 'true');
    } catch {
      setDesktopEnabledState(false);
    }
    const sync = () => setDesktopEnabledState(window.localStorage.getItem(DESKTOP_KEY) === 'true');
    window.addEventListener('scanner-desktop-alerts-updated', sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener('scanner-desktop-alerts-updated', sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  const requestDesktopPermission = useCallback(async () => {
    if (typeof window === 'undefined' || !('Notification' in window)) return 'unsupported' as const;
    if (window.Notification.permission === 'granted') return 'granted';
    if (window.Notification.permission === 'denied') return 'denied';
    return window.Notification.requestPermission();
  }, []);

  const setDesktopEnabled = useCallback(async (enabled: boolean) => {
    if (enabled) {
      const permission = await requestDesktopPermission();
      if (permission !== 'granted') {
        enabled = false;
      }
    }
    window.localStorage.setItem(DESKTOP_KEY, enabled ? 'true' : 'false');
    setDesktopEnabledState(enabled);
    window.dispatchEvent(new Event('scanner-desktop-alerts-updated'));
  }, [requestDesktopPermission]);

  const push = useCallback((message: string, type: ToastType = 'info', options: PushOptions = {}) => {
    const dedupeKey = options.dedupeKey || `${type}:${message}`;
    const count = options.persist === false ? 1 : appendNotification(message, type, dedupeKey);
    const now = Date.now();
    const last = recentRef.current.get(dedupeKey) || 0;
    if (now - last < DEDUPE_MS) {
      return;
    }
    recentRef.current.set(dedupeKey, now);

    if ((options.desktop || type === 'error' || type === 'warning') && desktopEnabledState && 'Notification' in window && window.Notification.permission === 'granted') {
      new window.Notification('Scanner V20', { body: count > 1 ? `${message} (${count}x)` : message });
    }

    const id = String(Date.now()) + Math.random().toString(36).slice(2, 6);
    const t = { id, message, type, count };
    setList((s) => [t, ...s].slice(0, 4));
    setTimeout(() => setList((s) => s.filter(x => x.id !== id)), 6000);
  }, [desktopEnabledState]);

  const value = useMemo(() => ({ push, desktopEnabled: desktopEnabledState, setDesktopEnabled, requestDesktopPermission }), [push, desktopEnabledState, setDesktopEnabled, requestDesktopPermission]);

  return (
    <ToastCtx.Provider value={value}>
      {children}
      <div className="toast-stack" aria-live="polite" role="region">
        {list.map(t => (
          <div key={t.id} className={`toast toast--${t.type || 'info'}`}>
            <div className="toast-message">{t.message}</div>
            {Number(t.count || 1) > 1 && <small>{t.count} repeats</small>}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export default ToastProvider;
