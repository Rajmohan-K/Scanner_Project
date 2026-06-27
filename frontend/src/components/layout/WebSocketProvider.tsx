"use client";

import React, { useEffect, useRef } from 'react';
import { getApiBaseUrl } from '@/lib/api';
import { TickPayload, useLiveStockStore } from '@/hooks/useLiveStockStore';

type Transport = 'websocket' | 'sse' | 'polling';

function normalizeSymbol(payload: any) {
  return String(payload?.symbol || payload?.nse_symbol || payload?.isin || '').toUpperCase();
}

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const wsRef = useRef<WebSocket | null>(null);
  const sseRef = useRef<EventSource | null>(null);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastMessageAtRef = useRef<number>(0);
  const transportRef = useRef<Transport>('websocket');
  const attemptsRef = useRef(0);

  useEffect(() => {
    let active = true;
    const store = useLiveStockStore.getState();

    function clearTimers() {
      timersRef.current.forEach((timer) => clearTimeout(timer));
      timersRef.current = [];
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    }

    function cleanupTransport() {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (sseRef.current) {
        sseRef.current.close();
        sseRef.current = null;
      }
    }

    function schedule(fn: () => void, delay: number) {
      const timer = setTimeout(fn, delay);
      timersRef.current.push(timer);
    }

    function applyMessage(payload: any) {
      if (!active || !payload) return;
      lastMessageAtRef.current = Date.now();
      if (payload.type === 'heartbeat') {
        store.setConnectionStatus('Connected');
        store.setLastUpdated(payload.updated_at || new Date().toISOString());
        return;
      }
      if (payload.type === 'snapshot' || payload.type === 'SNAPSHOT') {
        store.applySnapshot(payload.snapshot || payload.data || {});
        store.setConnectionStatus('Connected');
        return;
      }
      if (payload.type === 'stock_update' || payload.type === 'TICK') {
        const symbol = normalizeSymbol(payload);
        if (symbol) store.updateTick(symbol, payload as TickPayload);
        store.setConnectionStatus('Connected');
      }
    }

    function connectPolling() {
      if (!active || pollingRef.current) return;
      transportRef.current = 'polling';
      store.setConnectionStatus('Reconnecting');
      pollingRef.current = setInterval(async () => {
        try {
          const response = await fetch(`${getApiBaseUrl()}/api/market/snapshot?_ts=${Date.now()}`);
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          const payload = await response.json();
          applyMessage({ type: 'snapshot', snapshot: payload.snapshot || {} });
        } catch {
          store.setConnectionStatus('Backend Down');
        }
      }, 5000);
    }

    function connectSse() {
      if (!active || sseRef.current) return;
      transportRef.current = 'sse';
      store.setConnectionStatus('Reconnecting');
      try {
        const source = new EventSource(`${getApiBaseUrl()}/events`);
        sseRef.current = source;
        source.onopen = () => {
          attemptsRef.current = 0;
          store.setConnectionStatus('Connected');
        };
        const onMessage = (event: MessageEvent) => {
          try {
            applyMessage(JSON.parse(event.data));
          } catch {
            // Ignore malformed stream packets; the heartbeat will keep state honest.
          }
        };
        ['snapshot', 'stock_update', 'TICK', 'heartbeat'].forEach((eventName) => {
          source.addEventListener(eventName, onMessage as EventListener);
        });
        source.onerror = () => {
          source.close();
          sseRef.current = null;
          store.setConnectionStatus('Reconnecting');
          schedule(connectPolling, 1500);
        };
      } catch {
        connectPolling();
      }
    }

    function connectWebSocket() {
      if (!active || wsRef.current) return;
      transportRef.current = 'websocket';
      store.setConnectionStatus(attemptsRef.current ? 'Reconnecting' : 'Connecting');
      try {
        const ws = new WebSocket(`${getApiBaseUrl().replace(/^http/, 'ws')}/live`);
        wsRef.current = ws;
        let pingTimer: ReturnType<typeof setInterval> | null = null;
        ws.onopen = () => {
          attemptsRef.current = 0;
          store.setConnectionStatus('Connected');
          pingTimer = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }));
          }, 5000);
        };
        ws.onmessage = (event) => {
          try {
            applyMessage(JSON.parse(event.data));
          } catch {
            // Ignore malformed websocket packets.
          }
        };
        ws.onclose = () => {
          if (pingTimer) clearInterval(pingTimer);
          wsRef.current = null;
          if (!active) return;
          attemptsRef.current += 1;
          store.setConnectionStatus('Reconnecting');
          if (attemptsRef.current >= 3) {
            connectSse();
            return;
          }
          schedule(connectWebSocket, Math.min(1000 * 2 ** attemptsRef.current, 8000));
        };
        ws.onerror = () => {
          ws.close();
        };
      } catch {
        connectSse();
      }
    }

    const staleTimer = setInterval(() => {
      if (!active) return;
      const silentFor = Date.now() - lastMessageAtRef.current;
      if (lastMessageAtRef.current && silentFor > 15000 && useLiveStockStore.getState().connectionStatus === 'Connected') {
        store.setConnectionStatus('Stale Data');
      }
    }, 5000);

    lastMessageAtRef.current = Date.now();
    connectSse();

    return () => {
      active = false;
      clearInterval(staleTimer);
      clearTimers();
      cleanupTransport();
    };
  }, []);

  return <>{children}</>;
}

export default WebSocketProvider;
