import { useCallback, useEffect, useRef } from 'react';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL;
const STREAM_URL = process.env.NEXT_PUBLIC_STREAM_URL;

function apiBaseUrl() {
  if (STREAM_URL) return STREAM_URL.replace(/\/api\/stream$/, '');
  const mode = typeof window !== 'undefined' ? window.localStorage.getItem('scanner-api-target') : 'local';
  if (mode === 'server') return 'http://16.176.23.42:5000';
  return process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:5000';
}

export function useRealtime(onMessage?: (payload: any) => void) {
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const attemptsRef = useRef(0);
  const onMessageRef = useRef(onMessage);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  const connect = useCallback(() => {
    if (!WS_URL) {
      if (typeof window === 'undefined' || eventSourceRef.current) return;
      try {
        const source = new EventSource(STREAM_URL || `${apiBaseUrl()}/api/stream`);
        eventSourceRef.current = source;
        const handleMessage = (event: MessageEvent) => {
          if (!onMessageRef.current) return;
          try {
            onMessageRef.current(JSON.parse(event.data));
          } catch (error) {
            console.warn('SSE parse error', error);
          }
        };
        ['QUOTE_UPDATED', 'SCANNER_UPDATED', 'OPPORTUNITY_UPDATED', 'ALERT_TRIGGERED', 'AI_SCORE_CHANGED', 'ML_SCORE_CHANGED', 'META_SCORE_CHANGED'].forEach((eventName) => {
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
    if (attemptsRef.current >= 3) return;

    try {
      const socket = new WebSocket(WS_URL);
      socketRef.current = socket;

      socket.addEventListener('open', () => {
        console.log('WebSocket connected');
        attemptsRef.current = 0;
      });

      socket.addEventListener('message', (event) => {
        if (onMessageRef.current) {
          try {
            const payload = JSON.parse(event.data);
            onMessageRef.current(payload);
          } catch (error) {
            console.warn('WebSocket parse error', error);
          }
        }
      });

      socket.addEventListener('error', () => {
        console.warn(`WebSocket error (attempt ${attemptsRef.current + 1}/3)`);
      });

      socket.addEventListener('close', () => {
        socketRef.current = null;
        if (attemptsRef.current < 3) {
          const delay = Math.min(1000 * Math.pow(2, attemptsRef.current), 8000);
          attemptsRef.current += 1;
          reconnectTimeoutRef.current = setTimeout(connect, delay);
        }
      });
    } catch (err) {
      console.warn('WebSocket creation failed', err);
    }
  }, []);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.close();
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [connect]);
}

export function useRealtimeOptional(onMessage?: (payload: any) => void) {
  useRealtime(onMessage);
}
