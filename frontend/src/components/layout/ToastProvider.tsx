"use client";
import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';

type Toast = { id: string; type?: 'info'|'success'|'error'|'warning'; message: string };

const ToastCtx = createContext<{ push: (message: string, type?: 'info'|'success'|'error'|'warning') => void } | null>(null);

export function useToast() {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [list, setList] = useState<Toast[]>([]);

  const push = useCallback((message: string, type: Toast['type'] = 'info') => {
    const id = String(Date.now()) + Math.random().toString(36).slice(2, 6);
    const t = { id, message, type };
    setList((s) => [t, ...s]);
    setTimeout(() => setList((s) => s.filter(x => x.id !== id)), 6000);
  }, []);

  const value = useMemo(() => ({ push }), [push]);

  return (
    <ToastCtx.Provider value={value}>
      {children}
      <div className="toast-stack" aria-live="polite" role="region">
        {list.map(t => (
          <div key={t.id} className={`toast toast--${t.type || 'info'}`}>
            <div className="toast-message">{t.message}</div>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export default ToastProvider;
