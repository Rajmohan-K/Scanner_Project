import { useCallback, useEffect, useRef } from 'react';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL;

export function useRealtime(onMessage?: (payload: any) => void) {
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const attemptsRef = useRef(0);

  const connect = useCallback(() => {
    if (!WS_URL) return;
    if (attemptsRef.current >= 3) return;

    try {
      const socket = new WebSocket(WS_URL);
      socketRef.current = socket;

      socket.addEventListener('open', () => {
        console.log('WebSocket connected');
        attemptsRef.current = 0;
      });

      socket.addEventListener('message', (event) => {
        if (onMessage) {
          try {
            const payload = JSON.parse(event.data);
            onMessage(payload);
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
  }, [onMessage]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.close();
    };
  }, [connect]);
}

export function useRealtimeOptional(onMessage?: (payload: any) => void) {
  useRealtime(onMessage);
}
