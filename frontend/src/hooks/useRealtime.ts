import { useEffect, useRef } from 'react';
import { useMarketStore, TickPayload } from './useMarketStore';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL;
const STREAM_URL = process.env.NEXT_PUBLIC_STREAM_URL;

function apiBaseUrl() {
  if (STREAM_URL) return STREAM_URL.replace(/\/api\/stream$/, '');
  const mode = typeof window !== 'undefined' ? window.localStorage.getItem('scanner-api-target') : 'local';
  if (mode === 'server') return 'http://16.176.23.42:5000';
  return process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:5000';
}

type Listener = (payload: any) => void;
const listeners = new Set<Listener>();

let sharedWebSocket: WebSocket | null = null;
let sharedEventSource: EventSource | null = null;
let reconnectTimeout: NodeJS.Timeout | null = null;
let attempts = 0;

function connectShared() {
  if (typeof window === 'undefined') return;

  // Use SSE (EventSource) if WS_URL is not set
  if (!WS_URL) {
    if (sharedEventSource) return;
    try {
      // Connect to the unified market stream which aggregates both ticker quotes and events
      const source = new EventSource(STREAM_URL || `${apiBaseUrl()}/api/market/stream`);
      sharedEventSource = source;
      
      const handleMessage = (event: MessageEvent) => {
        try {
          const payload = JSON.parse(event.data);
          
          // Fallback tick update directly to market store
          if (payload && (payload.type === 'TICK' || payload.type === 'stock_update') && payload.symbol) {
            useMarketStore.getState().updateTick(payload.symbol, payload as TickPayload);
          }
          if (payload && (payload.type === 'snapshot' || payload.type === 'SNAPSHOT')) {
            useMarketStore.getState().applySnapshot(payload.snapshot || payload.data || {});
          }
          if (payload && payload.type === 'heartbeat') {
            useMarketStore.getState().setConnectionStatus('Connected');
            useMarketStore.getState().setLastUpdated(payload.updated_at || new Date().toISOString());
          }
          
          listeners.forEach((listener) => {
            try {
              listener(payload);
            } catch (err) {
              console.error('Error invoking real-time listener:', err);
            }
          });
        } catch (error) {
          console.warn('SSE parse error', error);
        }
      };

      const eventNames = [
        'TICK',
        'stock_update',
        'snapshot',
        'heartbeat',
        'QUOTE_UPDATED',
        'SCANNER_UPDATED',
        'OPPORTUNITY_UPDATED',
        'ALERT_TRIGGERED',
        'AI_SCORE_CHANGED',
        'ML_SCORE_CHANGED',
        'META_SCORE_CHANGED',
      ];
      eventNames.forEach((eventName) => {
        source.addEventListener(eventName, handleMessage as EventListener);
      });

      source.onerror = () => {
        console.warn('SSE connection interrupted; browser will retry automatically');
      };
    } catch (err) {
      console.warn('SSE creation failed', err);
    }
    return;
  }

  // Use WebSocket if WS_URL is set
  if (sharedWebSocket || attempts >= 3) return;

  try {
    const socket = new WebSocket(WS_URL);
    sharedWebSocket = socket;

    socket.addEventListener('open', () => {
      console.log('WebSocket connected');
      attempts = 0;
    });

    socket.addEventListener('message', (event) => {
      try {
        const payload = JSON.parse(event.data);
        listeners.forEach((listener) => {
          try {
            listener(payload);
          } catch (err) {
            console.error('Error invoking real-time listener:', err);
          }
        });
      } catch (error) {
        console.warn('WebSocket parse error', error);
      }
    });

    socket.addEventListener('error', () => {
      console.warn(`WebSocket error (attempt ${attempts + 1}/3)`);
    });

    socket.addEventListener('close', () => {
      sharedWebSocket = null;
      if (attempts < 3) {
        const delay = Math.min(1000 * Math.pow(2, attempts), 8000);
        attempts += 1;
        if (reconnectTimeout) clearTimeout(reconnectTimeout);
        reconnectTimeout = setTimeout(connectShared, delay);
      }
    });
  } catch (err) {
    console.warn('WebSocket creation failed', err);
  }
}

function disconnectShared() {
  if (reconnectTimeout) {
    clearTimeout(reconnectTimeout);
    reconnectTimeout = null;
  }
  if (sharedWebSocket) {
    if (sharedWebSocket.readyState === WebSocket.OPEN) {
      sharedWebSocket.close();
    }
    sharedWebSocket = null;
  }
  if (sharedEventSource) {
    sharedEventSource.close();
    sharedEventSource = null;
  }
}

export function useRealtime(onMessage?: (payload: any) => void) {
  const onMessageRef = useRef(onMessage);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    const listener: Listener = (payload) => {
      if (onMessageRef.current) {
        onMessageRef.current(payload);
      }
    };

    listeners.add(listener);
    
    // Connect if this is the first listener
    if (listeners.size === 1) {
      connectShared();
    }

    return () => {
      listeners.delete(listener);
      
      // Clean up connection if there are no listeners left
      if (listeners.size === 0) {
        disconnectShared();
      }
    };
  }, []);
}

export function useRealtimeOptional(onMessage?: (payload: any) => void) {
  useRealtime(onMessage);
}

