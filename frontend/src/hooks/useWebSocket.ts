import { useEffect, useRef, useState } from 'react';
import { useMarketStore, TickPayload } from './useMarketStore';
import { getApiBaseUrl } from '@/lib/api';

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<'Connecting' | 'Connected' | 'Reconnecting' | 'Backend Down'>('Connecting');
  const updateTick = useMarketStore((state) => state.updateTick);
  const setGlobalStatus = useMarketStore((state) => state.setConnectionStatus);
  const applySnapshot = useMarketStore((state) => state.applySnapshot);

  useEffect(() => {
    let active = true;
    let reconnectTimeout: number;
    let heartbeatInterval: number;
    let attempts = 0;

    function connect() {
      if (!active) return;
      const baseUrl = getApiBaseUrl();
      const wsUrl = baseUrl.replace(/^http/, 'ws') + '/live';
      const nextStatus = attempts ? 'Reconnecting' : 'Connecting';
      setConnectionStatus(nextStatus);
      setGlobalStatus(nextStatus);

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!active) return;
        attempts = 0;
        setConnectionStatus('Connected');
        setGlobalStatus('Connected');
        heartbeatInterval = window.setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }));
        }, 5000);
      };

      ws.onmessage = (event) => {
        if (!active) return;
        try {
          const payload = JSON.parse(event.data);
          if (payload && (payload.type === 'TICK' || payload.type === 'stock_update') && payload.symbol) {
            updateTick(payload.symbol, payload as TickPayload);
          }
          if (payload && (payload.type === 'snapshot' || payload.type === 'SNAPSHOT')) {
            applySnapshot(payload.snapshot || payload.data || {});
          }
        } catch (err) {
          console.error('Error parsing WebSocket message:', err);
        }
      };

      ws.onerror = (err) => {
        console.error('Market WebSocket error:', err);
      };

      ws.onclose = () => {
        if (!active) return;
        window.clearInterval(heartbeatInterval);
        attempts += 1;
        const status = attempts > 6 ? 'Backend Down' : 'Reconnecting';
        setConnectionStatus(status);
        setGlobalStatus(status);
        reconnectTimeout = window.setTimeout(connect, Math.min(1000 * 2 ** attempts, 10000));
      };
    }

    connect();

    return () => {
      active = false;
      window.clearTimeout(reconnectTimeout);
      window.clearInterval(heartbeatInterval);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [applySnapshot, setGlobalStatus, updateTick]);

  return { connectionStatus };
}
