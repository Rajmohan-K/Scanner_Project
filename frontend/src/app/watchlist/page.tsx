"use client";

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Bell, BellOff, History, Pin, PinOff, Plus, RefreshCw, RotateCcw, Save, Settings2, ShieldCheck, Trash2 } from 'lucide-react';
import {
  addWatchlistItem,
  deleteWatchlistItem,
  getAlertSettings,
  getWatchlist,
  getWatchlistHistory,
  getWatchlistStreamUrl,
  saveAlertSettings,
  updateWatchlistItem,
  AlertHistoryRecord,
  WatchlistItem,
  getWatchlistAudit,
  clearWatchlistAudit,
  type WatchlistAuditRecord,
  getGrowwIntradayStocks,
} from '@/lib/api';
import {
  DEFAULT_WATCHLIST_ALERT_SETTINGS,
  desktopDeliveryLabel,
  readWatchlistAlertSettings,
  storeWatchlistAlertSettings,
  WATCHLIST_ALERT_EVENT,
} from '@/lib/watchlistAlerts';
import { PageHero, TerminalPanel, DataTable } from '@/components/terminal/TerminalPrimitives';
import { useToast } from '@/components/layout/ToastProvider';

const DEFAULT_ALERT_SETTINGS = DEFAULT_WATCHLIST_ALERT_SETTINGS;

function readStoredAlertSettings() {
  return readWatchlistAlertSettings();
}

function storeAlertSettingsLocal(settings: Record<string, any>) {
  storeWatchlistAlertSettings(settings);
}

function formatNumber(value: unknown, digits = 2) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : '-';
}

function formatTime(value?: string) {
  if (!value) return '-';
  return new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  }).format(new Date(value));
}

function statusTone(status?: string) {
  const value = String(status || '').toLowerCase();
  if (value.includes('ready') || value.includes('confirmed') || value.includes('breakout') || value.includes('near')) return 'good';
  if (value.includes('avoid') || value.includes('breakdown') || value.includes('failed')) return 'bad';
  return 'warn';
}

function actionTone(action?: string) {
  const value = String(action || '').toLowerCase();
  if (value.includes('buy') || value.includes('book') || value.includes('trail')) return 'good';
  if (value.includes('avoid') || value.includes('exit')) return 'bad';
  return 'warn';
}

function formatCurrency(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? `INR ${number.toFixed(2)}` : '-';
}

function getStockPriorityScore(item: WatchlistItem, pinnedSymbols: string[] = []): number {
  const snap = item.snapshot || {};
  const action = String(snap.action || '').toUpperCase();
  const readiness = String(snap.trade_readiness || '').toUpperCase();
  const status = String(snap.current_status || '').toUpperCase();

  let score = 0;

  // Pinned status gets the absolute highest priority boost
  if (pinnedSymbols.includes(item.symbol)) {
    score += 1000000;
  }

  // 1. Action rules
  if (action === 'BUY READY' || action === 'BUY') score += 10000;
  else if (action === 'BOOK 50%') score += 9000;
  else if (action === 'TRAIL SL') score += 8000;
  else if (action === 'EXIT') score += 7000;
  else if (action === 'WAIT') score += 5000;
  else if (action === 'ALERT ONLY') score += 4000;
  else if (action === 'WATCH') score += 3000;
  else if (action === 'AVOID') score -= 5000;

  // 2. Readiness rules
  if (readiness === 'TRADE READY' || readiness === 'BREAKOUT CONFIRMED') score += 1000;
  else if (readiness === 'NEAR BREAKOUT') score += 800;
  else if (readiness === 'VOLUME PENDING') score += 600;
  else if (readiness === 'WAITING UNTIL 11 AM') score += 500;
  else if (readiness === 'OPENING VOLATILITY - WAIT') score += 400;
  else if (readiness === 'NOT READY') score += 100;
  else if (readiness === 'AVOID') score -= 1000;

  // 3. Status rules
  if (status === 'JUST BREAKOUT') score += 500;
  else if (status === 'ABOUT TO BREAKOUT') score += 400;
  else if (status === 'NEAR BREAKOUT') score += 300;
  else if (status === 'PULLBACK') score += 200;
  else if (status === 'CONSOLIDATING') score += 100;
  else if (status === 'FAILED BREAKOUT') score -= 200;
  else if (status === 'BREAKDOWN RISK') score -= 500;
  else if (status === 'AVOID') score -= 1000;

  return score;
}

export default function WatchlistPage() {
  const toast = useToast();
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [symbol, setSymbol] = useState('');
  const [selected, setSelected] = useState<WatchlistItem | null>(null);
  const [settings, setSettings] = useState<Record<string, any>>(DEFAULT_ALERT_SETTINGS);
  const [history, setHistory] = useState<AlertHistoryRecord[]>([]);
  const [auditHistory, setAuditHistory] = useState<WatchlistAuditRecord[]>([]);
  const [historyFilters, setHistoryFilters] = useState<Record<string, string>>({});
  const [connection, setConnection] = useState('Connecting');
  const [settingsDirty, setSettingsDirty] = useState(false);
  const settingsLoaded = useRef(false);

  const [filterQuery, setFilterQuery] = useState('');
  const [filterReadiness, setFilterReadiness] = useState('');
  const [filterAction, setFilterAction] = useState('');
  const [filterAlerts, setFilterAlerts] = useState('');
  const [showSettings, setShowSettings] = useState(false);

  const [pinnedSymbols, setPinnedSymbols] = useState<string[]>(() => {
    if (typeof window !== 'undefined') {
      try {
        const stored = window.localStorage.getItem('scanner-watchlist-pinned-symbols');
        return stored ? JSON.parse(stored) : [];
      } catch {
        return [];
      }
    }
    return [];
  });

  const togglePinSymbol = (symbol: string) => {
    setPinnedSymbols((current) => {
      const isPinned = current.includes(symbol);
      const next = isPinned ? current.filter((s) => s !== symbol) : [...current, symbol];
      if (typeof window !== 'undefined') {
        window.localStorage.setItem('scanner-watchlist-pinned-symbols', JSON.stringify(next));
      }
      toast.push(isPinned ? `${symbol} unpinned` : `${symbol} pinned to top`, 'success');
      return next;
    });
  };

  const filteredItems = useMemo(() => {
    const list = items.filter((item) => {
      const snap = item.snapshot || {};
      
      if (filterQuery) {
        const query = filterQuery.toLowerCase();
        const matchesSym = item.symbol.toLowerCase().includes(query);
        const matchesCompany = (snap.company_name || item.company_name || '').toLowerCase().includes(query);
        if (!matchesSym && !matchesCompany) return false;
      }
      
      if (filterReadiness) {
        const readiness = String(snap.trade_readiness || '').toLowerCase();
        if (!readiness.includes(filterReadiness.toLowerCase())) return false;
      }
      
      if (filterAction) {
        const action = String(snap.action || '').toLowerCase();
        if (!action.includes(filterAction.toLowerCase())) return false;
      }
      
      if (filterAlerts) {
        const isEnabled = item.alerts_enabled !== false;
        if (filterAlerts === 'on' && !isEnabled) return false;
        if (filterAlerts === 'off' && isEnabled) return false;
      }
      
      return true;
    });

    return list.sort((a, b) => {
      const scoreA = getStockPriorityScore(a, pinnedSymbols);
      const scoreB = getStockPriorityScore(b, pinnedSymbols);
      if (scoreA !== scoreB) {
        return scoreB - scoreA;
      }
      
      // If scores are equal, sort by distance to breakout (smaller distance first)
      const distA = a.snapshot?.distance_to_breakout_pct ?? 999;
      const distB = b.snapshot?.distance_to_breakout_pct ?? 999;
      if (distA !== distB) {
        return distA - distB;
      }

      return a.symbol.localeCompare(b.symbol);
    });
  }, [items, filterQuery, filterReadiness, filterAction, filterAlerts, pinnedSymbols]);

  async function load() {
    setLoading(true);
    setError('');
    try {
      const [watchlist, alertSettings, auditResponse] = await Promise.all([
        getWatchlist(),
        getAlertSettings(),
        getWatchlistAudit()
      ]);
      const storedSettings = readStoredAlertSettings();
      const mergedSettings = {
        ...DEFAULT_ALERT_SETTINGS,
        ...(alertSettings.settings || {}),
        ...storedSettings,
      };
      setItems(watchlist.items || []);
      setSettings(mergedSettings);
      storeAlertSettingsLocal(mergedSettings);
      const historyResponse = await getWatchlistHistory({ limit: 80 });
      setHistory(historyResponse.alerts || []);
      setAuditHistory(auditResponse.audit || []);
    } catch (err: any) {
      const storedSettings = readStoredAlertSettings();
      setSettings((current) => ({
        ...DEFAULT_ALERT_SETTINGS,
        ...current,
        ...storedSettings,
      }));
      setError(`${err?.message || 'Unable to load watchlist'} - backend may need restart on port 5000`);
    } finally {
      settingsLoaded.current = true;
      setLoading(false);
    }
  }

  useEffect(() => {
    const storedSettings = readStoredAlertSettings();
    if (Object.keys(storedSettings).length) {
      setSettings({ ...DEFAULT_ALERT_SETTINGS, ...storedSettings });
    }
    load();
  }, []);

  useEffect(() => {
    if (!settingsLoaded.current || !settingsDirty) return;
    const timer = window.setTimeout(async () => {
      try {
        const response = await saveAlertSettings(settings);
        const savedSettings = { ...DEFAULT_ALERT_SETTINGS, ...(response.settings || settings) };
        setSettings(savedSettings);
        storeAlertSettingsLocal(savedSettings);
        setSettingsDirty(false);
      } catch {
        // Keep the local draft. The explicit Save button reports backend errors.
      }
    }, 700);
    return () => window.clearTimeout(timer);
  }, [settings, settingsDirty]);

  useEffect(() => {
    const source = new EventSource(getWatchlistStreamUrl());
    source.onopen = () => setConnection('Live');
    source.onerror = () => setConnection('Reconnecting');
    source.addEventListener('WATCHLIST_UPDATED', (event) => {
      try {
        const payload = JSON.parse((event as MessageEvent).data);
        setItems(payload.items || []);
        const alerts = payload.alerts || [];
        if (Array.isArray(alerts)) {
          setHistory(alerts);
        }
        if (payload.audit && Array.isArray(payload.audit)) {
          setAuditHistory(payload.audit);
        }
      } catch {
        setConnection('Stream error');
      }
    });
    return () => source.close();
  }, []);

  useEffect(() => {
    function handleAlert(event: Event) {
      const alert = (event as CustomEvent<AlertHistoryRecord>).detail;
      if (!alert?.alert_id) return;
      setHistory((current) => [alert, ...current.filter((row) => row.alert_id !== alert.alert_id)].slice(0, 100));
    }
    window.addEventListener(WATCHLIST_ALERT_EVENT, handleAlert);
    return () => window.removeEventListener(WATCHLIST_ALERT_EVENT, handleAlert);
  }, []);

  const stats = useMemo(() => {
    const monitored = items.filter((item) => item.monitoring_enabled !== false).length;
    const alerts = items.filter((item) => item.alerts_enabled !== false).length;
    const tradeReady = items.filter((item) => String(item.snapshot?.trade_readiness || '').toLowerCase().includes('ready')).length;
    const wait = items.filter((item) => String(item.snapshot?.action || '').toLowerCase() === 'wait').length;
    return { monitored, alerts, tradeReady, wait };
  }, [items]);

  async function addSymbol() {
    const raw = symbol.trim();
    if (!raw) return;
    try {
      const response = await addWatchlistItem({ symbol: raw, monitoring_enabled: true, alerts_enabled: true, telegram_enabled: false });
      setSymbol('');
      if (response.items && Array.isArray(response.items)) {
        setItems((current) => {
          const newSyms = new Set(response.items!.map((item) => item.symbol));
          return [...response.items!, ...current.filter((item) => !newSyms.has(item.symbol))];
        });
        const addedNames = response.items.map((item) => item.symbol).join(', ');
        toast.push(`${addedNames} added to watchlist monitor`, 'success');
      } else {
        setItems((current) => [response.item, ...current.filter((item) => item.symbol !== response.item.symbol)]);
        toast.push(`${response.item.symbol} added to watchlist monitor`, 'success');
      }
    } catch (err: any) {
      toast.push(err?.message || 'Unable to add symbol. Check backend is running on port 5000.', 'error');
    }
  }

  async function patchItem(item: WatchlistItem, payload: Partial<WatchlistItem>) {
    try {
      const response = await updateWatchlistItem(item.symbol, payload);
      setItems((current) => current.map((row) => (row.symbol === item.symbol ? response.item : row)));
      setSelected((current) => (current?.symbol === item.symbol ? response.item : current));
    } catch (err: any) {
      toast.push(err?.message || 'Unable to update watchlist symbol', 'error');
    }
  }

  async function removeSymbol(item: WatchlistItem) {
    try {
      await deleteWatchlistItem(item.symbol);
      setItems((current) => current.filter((row) => row.symbol !== item.symbol));
      setSelected((current) => (current?.symbol === item.symbol ? null : current));
      toast.push(`${item.symbol} removed`, 'success');
    } catch (err: any) {
      toast.push(err?.message || 'Unable to remove symbol', 'error');
    }
  }

  async function pullGrowwStocks() {
    try {
      const { readGrowwResults } = await import('@/lib/growwIntraday');
      let priorityRows = readGrowwResults().priorityRows || [];
      if (!priorityRows.length) {
        toast.push('No cached Groww priority stocks found. Fetching from Groww source...', 'info');
        const payload = await getGrowwIntradayStocks(50);
        const resolvedRows = payload.rows || [];
        const { buildGrowwPriorityRows } = await import('@/lib/growwIntraday');
        priorityRows = buildGrowwPriorityRows(resolvedRows);
      }
      
      const symbols = priorityRows
        .map((r: any) => r.symbol)
        .filter(Boolean);
        
      if (!symbols.length) {
        toast.push('No qualified priority stocks found in Groww source. Run scan on Groww page first.', 'warning');
        return;
      }
      
      const symbolsString = symbols.join(',');
      const response = await addWatchlistItem({
        symbol: symbolsString,
        monitoring_enabled: true,
        alerts_enabled: true,
      });
      
      if (response.items) {
        setItems(response.items);
      }
      toast.push(`Successfully imported ${symbols.length} priority stocks from Groww source: ${symbols.join(', ')}`, 'success');
    } catch (err: any) {
      toast.push(err?.message || 'Failed to pull Groww stocks', 'error');
    }
  }

  async function clearAuditHistory() {
    try {
      await clearWatchlistAudit();
      setAuditHistory([]);
      toast.push('Watchlist outcome audit logs cleared', 'success');
    } catch (err: any) {
      toast.push(err?.message || 'Failed to clear audit logs', 'error');
    }
  }

  async function saveGlobalSettings() {
    storeAlertSettingsLocal(settings);
    try {
      const response = await saveAlertSettings(settings);
      const savedSettings = { ...DEFAULT_ALERT_SETTINGS, ...(response.settings || settings) };
      setSettings(savedSettings);
      storeAlertSettingsLocal(savedSettings);
      setSettingsDirty(false);
      toast.push('Alert settings saved', 'success');
    } catch (err: any) {
      toast.push(`${err?.message || 'Unable to sync alert settings to backend.'} Changes remain saved in this browser.`, 'error');
    }
  }

  function updateGlobalSettings(patch: Record<string, any>) {
    setSettings((current) => {
      const nextSettings = { ...current, ...patch };
      storeAlertSettingsLocal(nextSettings);
      return nextSettings;
    });
    setSettingsDirty(true);
  }

  function resetDefaults() {
    const defaults = { ...DEFAULT_ALERT_SETTINGS };
    setSettings(defaults);
    storeAlertSettingsLocal(defaults);
    setSettingsDirty(true);
    toast.push('Suggested alert defaults restored and saved locally.', 'success');
  }

  async function refreshHistory(nextFilters = historyFilters) {
    try {
      const response = await getWatchlistHistory({ ...nextFilters, limit: 100 });
      setHistory(response.alerts || []);
    } catch (err: any) {
      toast.push(err?.message || 'Unable to load alert history', 'error');
    }
  }

  async function requestDesktopPermission() {
    if (typeof window === 'undefined' || !('Notification' in window)) {
      toast.push('Desktop notifications are not supported in this browser.', 'error');
      return;
    }
    const permission = await Notification.requestPermission();
    toast.push(`Desktop notification permission: ${permission}`, permission === 'granted' ? 'success' : 'error');
  }

  return (
    <main>
      <PageHero
        eyebrow="Watchlist Monitoring"
        title="Watchlist Monitor"
        description="Backend-monitored symbols with strict time, volume, SL, GTT, profit-booking, desktop, and Telegram alert readiness. Manual confirmation required; auto trading disabled."
        actions={<>
          <button className="btn-secondary" type="button" onClick={load}><RefreshCw size={16} /> Refresh</button>
          <button className="btn-secondary" type="button" onClick={requestDesktopPermission}><Bell size={16} /> Browser Alerts</button>
          <button className="btn-secondary" type="button" onClick={() => setShowSettings(!showSettings)}><Settings2 size={16} /> {showSettings ? 'Hide Config' : 'Global Config'}</button>
          <button className="btn-primary" type="button" onClick={saveGlobalSettings}><Save size={16} /> Save Config</button>
        </>}
        metrics={[
          { label: 'Conn', value: connection, tone: connection === 'Live' ? 'good' : 'warn' },
          { label: 'Monitored', value: String(stats.monitored) },
          { label: 'Alerts', value: String(stats.alerts) },
          { label: 'Ready', value: String(stats.tradeReady), tone: stats.tradeReady ? 'good' : 'warn' },
          { label: 'Waiting', value: String(stats.wait), tone: stats.wait ? 'warn' : 'good' },
        ]}
      />

      <div style={{ 
        display: 'flex', 
        flexDirection: 'column', 
        padding: '0 16px', 
        gap: '8px', 
        marginBottom: '10px' 
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase' }}>Add Stock:</span>
          <input 
            value={symbol} 
            onChange={(event) => setSymbol(event.target.value.toUpperCase())} 
            placeholder="RELIANCE, TCS, MTARTECH" 
            onKeyDown={(event) => { if (event.key === 'Enter') addSymbol(); }}
            style={{ 
              padding: '3px 6px', 
              fontSize: '0.76rem', 
              width: '200px', 
              background: 'var(--panel-strong)', 
              border: '1px solid var(--border)',
              borderRadius: '4px',
              color: 'var(--text)'
            }}
          />
          <button className="btn-primary" type="button" onClick={addSymbol} style={{ padding: '3px 8px', fontSize: '0.72rem', minHeight: '26px' }}><Plus size={11} /> Add Stock</button>
          <button className="btn-secondary" type="button" onClick={resetDefaults} style={{ padding: '3px 8px', fontSize: '0.72rem', minHeight: '26px' }}><RotateCcw size={11} /> Reset Defaults</button>
          <button className="btn-secondary" type="button" onClick={pullGrowwStocks} style={{ padding: '3px 8px', fontSize: '0.72rem', minHeight: '26px' }}><Plus size={11} /> Pull Groww Source</button>
        </div>

        {showSettings && (
          <div style={{
            background: 'var(--surface-3)',
            border: '1px solid var(--border)',
            borderRadius: '6px',
            padding: '10px',
            marginTop: '2px'
          }}>
            <div className="settings-grid compact-settings-grid" style={{ margin: 0, gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '6px' }}>
              {[
                ['breakout_distance_pct', 'Breakout Distance %', 'Near resistance alert zone.'],
                ['breakout_volume_multiplier', 'Volume Multiplier', 'BUY volume multiplier.'],
                ['consecutive_candle_count', 'Candle Count', 'Consecutive candle alerts.'],
                ['price_move_pct_threshold', 'Price Move %', 'Single-candle move threshold.'],
                ['half_percent_move_threshold', 'Half % Move', 'Alert offset step.'],
                ['stop_loss_min_pct', 'SL Min %', 'Minimum stop loss.'],
                ['stop_loss_max_pct', 'SL Max %', 'Maximum risk stop loss.'],
                ['default_stop_loss_pct', 'Default SL %', 'GTT stop loss default.'],
                ['profit_booking_start_pct', 'Book Start %', '50% profit booking start.'],
                ['profit_booking_end_pct', 'Book End %', 'Profit booking zone end.'],
                ['book_partial_quantity_pct', 'Partial Qty %', 'Suggested partial exit qty.'],
                ['cooldown_seconds', 'Cooldown Seconds', 'Alert frequency cooldown.'],
                ['monitoring_interval_seconds', 'Monitor Interval', 'Backend check cycle.'],
              ].map(([key, label, hint]) => (
                <label key={key} style={{ display: 'flex', flexDirection: 'column', gap: '1px', fontSize: '0.65rem', padding: '4px', background: 'rgba(0,0,0,0.15)', border: '1px solid rgba(255,255,255,0.03)', borderRadius: '4px' }}>
                  <span style={{ color: 'var(--muted)', fontWeight: 700 }}>{label}</span>
                  <input 
                    type="number" 
                    value={settings[key] ?? ''} 
                    onChange={(event) => updateGlobalSettings({ [key]: Number(event.target.value) })} 
                    style={{ padding: '2px 4px', fontSize: '0.74rem', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '3px' }}
                  />
                  <small style={{ color: 'var(--muted)', fontSize: '0.6rem' }}>{hint}</small>
                </label>
              ))}
              <label style={{ display: 'flex', flexDirection: 'column', gap: '1px', fontSize: '0.65rem', padding: '4px', background: 'rgba(0,0,0,0.15)', border: '1px solid rgba(255,255,255,0.03)', borderRadius: '4px' }}>
                <span style={{ color: 'var(--muted)', fontWeight: 700 }}>First Window Ends</span>
                <input type="time" value={settings.first_30_minutes_wait_until ?? '09:45'} onChange={(event) => updateGlobalSettings({ first_30_minutes_wait_until: event.target.value })} style={{ padding: '2px 4px', fontSize: '0.74rem', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '3px' }} />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '1px', fontSize: '0.65rem', padding: '4px', background: 'rgba(0,0,0,0.15)', border: '1px solid rgba(255,255,255,0.03)', borderRadius: '4px' }}>
                <span style={{ color: 'var(--muted)', fontWeight: 700 }}>Confirm After</span>
                <input type="time" value={settings.confirmation_wait_until ?? '11:00'} onChange={(event) => updateGlobalSettings({ confirmation_wait_until: event.target.value })} style={{ padding: '2px 4px', fontSize: '0.74rem', background: 'var(--panel-strong)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '3px' }} />
              </label>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', marginTop: '8px', fontSize: '0.7rem', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '6px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={settings.watchlist_monitoring_enabled !== false} onChange={(event) => updateGlobalSettings({ watchlist_monitoring_enabled: event.target.checked })} /> Monitoring</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={settings.groww_source_enabled !== false} onChange={(event) => updateGlobalSettings({ groww_source_enabled: event.target.checked })} /> Fetch from Groww</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={settings.no_breakout_first_30_minutes !== false} onChange={(event) => updateGlobalSettings({ no_breakout_first_30_minutes: event.target.checked })} /> No BUY First 30m</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={settings.wait_until_11am_confirmation !== false} onChange={(event) => updateGlobalSettings({ wait_until_11am_confirmation: event.target.checked })} /> Wait Until 11 AM</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={settings.gtt_plan_enabled !== false} onChange={(event) => updateGlobalSettings({ gtt_plan_enabled: event.target.checked })} /> GTT Plan</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={Boolean(settings.market_hours_only)} onChange={(event) => updateGlobalSettings({ market_hours_only: event.target.checked })} /> Market Hours Only</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={settings.desktop_enabled !== false} onChange={(event) => updateGlobalSettings({ desktop_enabled: event.target.checked })} /> Desktop Alerts</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={Boolean(settings.sound_enabled)} onChange={(event) => updateGlobalSettings({ sound_enabled: event.target.checked })} /> Alert Sound</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}><input type="checkbox" checked={Boolean(settings.telegram_enabled)} onChange={(event) => updateGlobalSettings({ telegram_enabled: event.target.checked })} /> Telegram Alerts</label>
            </div>
            <div style={{ fontSize: '0.65rem', color: 'var(--muted)', marginTop: '6px', display: 'flex', alignItems: 'center', gap: '4px' }}><ShieldCheck size={12} /> Manual confirmation required. Auto buy/sell is disabled; use Groww GTT manually for Target/SL.</div>
          </div>
        )}
      </div>

      <TerminalPanel eyebrow="Live Table" title="Watched Stocks">
        {error && <div className="status-banner danger">{error}<button type="button" onClick={load}>Retry</button></div>}
        {loading ? (
          <div className="empty-state">Loading backend watchlist...</div>
        ) : items.length ? (
          <>
            <div className="watchlist-history-filters" style={{ marginBottom: '1.25rem' }}>
              <input 
                placeholder="Search symbol or company" 
                value={filterQuery} 
                onChange={(event) => setFilterQuery(event.target.value)} 
              />
              <select value={filterReadiness} onChange={(event) => setFilterReadiness(event.target.value)}>
                <option value="">All Readiness</option>
                <option value="ready">Trade Ready</option>
                <option value="wait">Opening Volatility / Wait</option>
                <option value="volume">Volume Pending</option>
                <option value="near">Near Breakout</option>
                <option value="avoid">Avoid</option>
                <option value="not">Not Ready</option>
              </select>
              <select value={filterAction} onChange={(event) => setFilterAction(event.target.value)}>
                <option value="">All Actions</option>
                <option value="buy">BUY READY</option>
                <option value="alert">ALERT ONLY</option>
                <option value="watch">WATCH</option>
                <option value="avoid">AVOID</option>
                <option value="exit">EXIT</option>
              </select>
              <select value={filterAlerts} onChange={(event) => setFilterAlerts(event.target.value)}>
                <option value="">All Alerts</option>
                <option value="on">Alerts On</option>
                <option value="off">Alerts Off</option>
              </select>
              <button className="btn-secondary" type="button" onClick={() => { setFilterQuery(''); setFilterReadiness(''); setFilterAction(''); setFilterAlerts(''); }}>
                Clear
              </button>
            </div>

            {filteredItems.length ? (
              <div className="terminal-table watchlist-monitor-table">
                 <div className="terminal-table-head">
                  {['Symbol', 'Company', 'Price', 'Change %', 'Vol vs Avg', 'Breakout', 'Distance', 'Status', 'Readiness', 'Action', 'Suggested Time', 'Entry', 'SL', 'Target 1', 'Target 2', 'Target 3', 'GTT Plan', 'Profit Booking', 'Last Alert', 'Last Alert Price', 'Checked', 'Alert Enabled', 'Actions'].map((heading) => <span key={heading}>{heading}</span>)}
                </div>
                {filteredItems.map((item) => {
                  const snap = item.snapshot || {};
                  const isSelected = selected?.symbol === item.symbol;
                  return (
                    <React.Fragment key={item.symbol}>
                      <article 
                        className={`terminal-table-row watchlist-monitor-row ${isSelected ? 'is-selected' : ''}`} 
                        onClick={() => setSelected(isSelected ? null : item)}
                        style={{ cursor: 'pointer' }}
                      >
                        <strong>
                          {pinnedSymbols.includes(item.symbol) && <Pin size={12} style={{ display: 'inline', marginRight: '4px', color: 'var(--accent)' }} />}
                          {item.symbol}
                        </strong>
                        <span>{snap.company_name || item.company_name || '-'}</span>
                        <span>{formatCurrency(snap.current_price)}</span>
                        <span className={Number(snap.price_change_pct) >= 0 ? 'positive' : 'negative'}>{formatNumber(snap.price_change_pct)}%</span>
                        <span>{formatNumber(snap.volume_spike)}x</span>
                        <span>{formatNumber(snap.breakout_level)}</span>
                        <span>{formatNumber(snap.distance_to_breakout_pct)}%</span>
                        <span className={`pill pill-${statusTone(snap.current_status)}`}>{snap.current_status || 'Checking'}</span>
                        <span className={`pill pill-${statusTone(snap.trade_readiness)}`}>{snap.trade_readiness || 'Not Ready'}</span>
                        <span className={`pill pill-${actionTone(snap.action)}`}>{snap.action || 'WATCH'}</span>
                        <span>{snap.suggested_time || '-'}</span>
                        <span>{formatCurrency(snap.entry)}</span>
                        <span>{formatCurrency(snap.stop_loss)}</span>
                        <span>{formatCurrency(snap.target1)}</span>
                        <span>{formatCurrency(snap.target2)}</span>
                        <span>{formatCurrency(snap.target3)}</span>
                        <span>{snap.gtt_plan ? 'Manual GTT Ready' : '-'}</span>
                        <span>{snap.profit_booking_status || '-'}</span>
                        <span>{item.last_alert || snap.last_alert || '-'}</span>
                        <span>{formatCurrency(snap.last_alert_price)}</span>
                        <span>{formatTime(item.last_checked || snap.last_checked)}</span>
                        <span>{item.alerts_enabled === false ? 'Off' : 'On'}</span>
                        <span className="row-actions">
                          <button 
                            className="icon-button" 
                            title={pinnedSymbols.includes(item.symbol) ? "Unpin stock" : "Pin stock"} 
                            type="button" 
                            onClick={(event) => { event.stopPropagation(); togglePinSymbol(item.symbol); }}
                          >
                            {pinnedSymbols.includes(item.symbol) ? <PinOff size={15} style={{ color: 'var(--accent)' }} /> : <Pin size={15} />}
                          </button>
                          <button className="icon-button" title="Toggle monitoring" type="button" onClick={(event) => { event.stopPropagation(); patchItem(item, { monitoring_enabled: item.monitoring_enabled === false }); }}>
                            {item.monitoring_enabled === false ? <BellOff size={15} /> : <Bell size={15} />}
                          </button>
                          <button className="icon-button" title="Remove" type="button" onClick={(event) => { event.stopPropagation(); removeSymbol(item); }}><Trash2 size={15} /></button>
                        </span>
                      </article>

                      {isSelected && (
                        <div 
                          className="custom-stock-detail-inline" 
                          onClick={(e) => e.stopPropagation()}
                          style={{ 
                            gridColumn: '1 / -1', 
                            background: 'rgba(10, 20, 35, 0.96)', 
                            borderTop: '1px solid var(--accent)', 
                            borderBottom: '1px solid var(--accent)', 
                            padding: '10px 14px',
                            color: 'var(--text)',
                            width: '100%',
                            minWidth: '2055px',
                            boxSizing: 'border-box'
                          }}
                        >
                          <div style={{
                            position: 'sticky',
                            left: '20px',
                            maxWidth: '1200px',
                            width: '100%',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '8px',
                          }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '6px' }}>
                              <h3 style={{ margin: 0, fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <strong style={{ color: 'var(--accent)' }}>{item.symbol}</strong>
                                <span style={{ fontSize: '0.78rem', color: 'var(--muted)' }}>{snap.company_name || item.company_name || '-'}</span>
                              </h3>
                              <div style={{ display: 'flex', gap: '4px' }}>
                                <button 
                                  className="btn-secondary" 
                                  type="button" 
                                  onClick={() => togglePinSymbol(item.symbol)}
                                  style={{ display: 'flex', alignItems: 'center', gap: '4px', padding: '2px 6px', fontSize: '0.72rem', minHeight: '22px' }}
                                >
                                  {pinnedSymbols.includes(item.symbol) ? (
                                    <>
                                      <PinOff size={11} /> Unpin
                                    </>
                                  ) : (
                                    <>
                                      <Pin size={11} /> Pin
                                    </>
                                  )}
                                </button>
                                <button 
                                  className="btn-secondary" 
                                  type="button" 
                                  onClick={() => setSelected(null)}
                                  style={{ padding: '2px 6px', fontSize: '0.72rem', minHeight: '22px', background: 'rgba(255, 100, 100, 0.1)', color: '#ff6b6b', border: '1px solid rgba(255, 100, 100, 0.2)' }}
                                >
                                  Close
                                </button>
                              </div>
                            </div>

                            <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1.1fr 0.9fr', gap: '16px' }}>
                              {/* Column 1: Analysis & Recommendation */}
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                                <span style={{ fontSize: '0.62rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--accent)' }}>Analysis & Booking Status</span>
                                <p style={{ margin: 0, fontSize: '0.76rem', lineHeight: '1.35', color: 'var(--text)', opacity: 0.9 }}>
                                  {snap.trade_reason || snap.reason || 'No active analysis available. Waiting for backend cycle.'}
                                </p>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '0.74rem' }}>
                                  <div>
                                    <span style={{ fontSize: '0.6rem', color: 'var(--muted)' }}>Suggested Time:</span>{' '}
                                    <strong style={{ color: 'var(--accent)' }}>{snap.suggested_time || '-'}</strong>
                                  </div>
                                  <div>
                                    <span style={{ fontSize: '0.6rem', color: 'var(--muted)' }}>Breakout Level:</span>{' '}
                                    <strong>{formatCurrency(snap.breakout_level)}</strong>
                                  </div>
                                  <div style={{ gridColumn: 'span 2' }}>
                                    <span style={{ fontSize: '0.6rem', color: 'var(--muted)' }}>Profit Booking:</span>{' '}
                                    <strong style={{ color: 'var(--accent)' }}>{snap.profit_booking_status || 'Not started'}</strong>
                                  </div>
                                </div>
                              </div>

                              {/* Column 2: Key Levels & Targets */}
                              <div>
                                <span style={{ fontSize: '0.62rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--accent)', display: 'block', marginBottom: '4px' }}>Key Levels & Targets</span>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 8px', fontSize: '0.74rem' }}>
                                  <div>
                                    <span style={{ fontSize: '0.6rem', color: 'var(--muted)', display: 'block' }}>Entry / Stop Loss</span>
                                    <strong>{formatCurrency(snap.entry)} / <span style={{ color: 'var(--negative)' }}>{formatCurrency(snap.stop_loss)}</span></strong>
                                  </div>
                                  <div>
                                    <span style={{ fontSize: '0.6rem', color: 'var(--muted)', display: 'block' }}>Risk / Confidence</span>
                                    <strong>{snap.risk || '-'} ({snap.risk_percent ? `${formatNumber(snap.risk_percent)}%` : '-'}) / {snap.confidence ? `${formatNumber(snap.confidence)}%` : '-'}</strong>
                                  </div>
                                  <div style={{ gridColumn: 'span 2' }}>
                                    <span style={{ fontSize: '0.6rem', color: 'var(--muted)', display: 'block' }}>GTT Targets (1 / 2 / 3)</span>
                                    <strong>{formatCurrency(snap.target1)} / {formatCurrency(snap.target2)} / {formatCurrency(snap.target3)}</strong>
                                  </div>
                                  <div>
                                    <span style={{ fontSize: '0.6rem', color: 'var(--muted)', display: 'block' }}>Support / Resistance</span>
                                    <strong>{formatCurrency(snap.support)} / {formatCurrency(snap.resistance)}</strong>
                                  </div>
                                  <div>
                                    <span style={{ fontSize: '0.6rem', color: 'var(--muted)', display: 'block' }}>VWAP / EMA 20</span>
                                    <strong>{formatCurrency(snap.vwap)} / {formatCurrency(snap.ema20)}</strong>
                                  </div>
                                </div>
                              </div>

                              {/* Column 3: Alert Configuration */}
                              <div>
                                <span style={{ fontSize: '0.62rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--accent)', display: 'block', marginBottom: '4px' }}>Alert Configuration</span>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 6px' }}>
                                  {[
                                    ['custom_breakout_price', 'Custom Breakout'],
                                    ['custom_support', 'Custom Support'],
                                    ['custom_resistance', 'Custom Resistance'],
                                    ['quantity_placeholder', 'Qty Config'],
                                    ['risk_amount_placeholder', 'Risk Config'],
                                    ['custom_candle_count', 'Candle Count'],
                                  ].map(([key, label]) => (
                                    <label key={key} style={{ display: 'flex', flexDirection: 'column', gap: '1px', fontSize: '0.64rem' }}>
                                      <span style={{ color: 'var(--muted)' }}>{label}</span>
                                      <input 
                                        type={key.includes('placeholder') ? 'text' : 'number'} 
                                        defaultValue={(item as any)[key] || ''} 
                                        onBlur={(event) => patchItem(item, { [key]: key.includes('placeholder') ? event.target.value : Number(event.target.value) } as any)} 
                                        style={{ 
                                          padding: '2px 4px', 
                                          fontSize: '0.72rem', 
                                          background: 'var(--panel-strong)', 
                                          border: '1px solid var(--border)', 
                                          borderRadius: '4px',
                                          color: 'var(--text)',
                                          width: '100%',
                                          boxSizing: 'border-box'
                                        }}
                                      />
                                    </label>
                                  ))}
                                </div>
                                <div style={{ display: 'flex', gap: '12px', marginTop: '6px', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '4px' }}>
                                  <label style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.7rem', cursor: 'pointer' }}>
                                    <input type="checkbox" checked={item.alerts_enabled !== false} onChange={(event) => patchItem(item, { alerts_enabled: event.target.checked })} /> Alerts
                                  </label>
                                  <label style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.7rem', cursor: 'pointer' }}>
                                    <input type="checkbox" checked={Boolean(item.telegram_enabled)} onChange={(event) => patchItem(item, { telegram_enabled: event.target.checked })} /> Telegram
                                  </label>
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                      )}
                    </React.Fragment>
                  );
                })}
              </div>
            ) : (
              <div className="empty-state">No matching stocks found.</div>
            )}
          </>
        ) : (
          <div className="empty-state">No stocks in watchlist. Add a symbol above to start monitoring.</div>
        )}
      </TerminalPanel>

      <TerminalPanel
        eyebrow="Alert History"
        title="Watchlist Notification Log"
        actions={<button className="btn-secondary" type="button" onClick={() => refreshHistory()}><History size={16} /> Refresh History</button>}
      >
        <div className="watchlist-history-filters">
          <input placeholder="Symbol" value={historyFilters.symbol || ''} onChange={(event) => setHistoryFilters((current) => ({ ...current, symbol: event.target.value.toUpperCase() }))} />
          <input placeholder="Alert type" value={historyFilters.alert_type || ''} onChange={(event) => setHistoryFilters((current) => ({ ...current, alert_type: event.target.value.toUpperCase() }))} />
          <input placeholder="Action" value={historyFilters.action || ''} onChange={(event) => setHistoryFilters((current) => ({ ...current, action: event.target.value.toUpperCase() }))} />
          <input type="date" value={historyFilters.date || ''} onChange={(event) => setHistoryFilters((current) => ({ ...current, date: event.target.value }))} />
          <select value={historyFilters.telegram_sent || ''} onChange={(event) => setHistoryFilters((current) => ({ ...current, telegram_sent: event.target.value }))}>
            <option value="">Telegram All</option>
            <option value="true">Telegram Sent</option>
            <option value="false">Telegram Not Sent</option>
          </select>
          <select value={historyFilters.trade_taken || ''} onChange={(event) => setHistoryFilters((current) => ({ ...current, trade_taken: event.target.value }))}>
            <option value="">Trade All</option>
            <option value="true">Taken</option>
            <option value="false">Not Taken</option>
          </select>
          <button className="btn-secondary" type="button" onClick={() => refreshHistory()}>Apply</button>
        </div>
        {history.length ? (
          <div className="terminal-table alert-history-table">
            <div className="terminal-table-head">
              {['Time', 'Symbol', 'Type', 'Action', 'Price', 'Entry', 'SL', 'Targets', 'Volume', 'Reason', 'Telegram', 'Desktop'].map((heading) => <span key={heading}>{heading}</span>)}
            </div>
            {history.map((alert) => (
              <article key={alert.alert_id} className="terminal-table-row alert-history-row">
                <span>{formatTime(alert.created_at)}</span>
                <strong>{alert.symbol}<small>{alert.severity}</small></strong>
                <span>{alert.alert_type}</span>
                <span className={`pill pill-${actionTone(alert.action)}`}>{alert.action || '-'}</span>
                <span>{formatCurrency(alert.trigger_price)}</span>
                <span>{formatCurrency(alert.entry)}</span>
                <span>{formatCurrency(alert.stop_loss)}</span>
                <span>{[alert.target1, alert.target2, alert.target3].filter(Boolean).map(formatCurrency).join(' / ') || '-'}</span>
                <span>{alert.volume_ratio ? `${formatNumber(alert.volume_ratio)}x` : '-'}</span>
                <span>{alert.reason || alert.message || '-'}</span>
                <span>{alert.telegram_sent ? 'Sent' : 'No'}</span>
                <span>{desktopDeliveryLabel(alert)}</span>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-state">No watchlist alerts yet. Alerts will appear after backend rules trigger.</div>
        )}
      </TerminalPanel>

      <TerminalPanel 
        eyebrow="Watchlist Audit" 
        title="Watchlist Outcomes & Comparison"
        actions={
          <button 
            className="btn-secondary" 
            type="button" 
            onClick={clearAuditHistory} 
            disabled={!auditHistory.length}
          >
            Clear Outcomes
          </button>
        }
      >
        <DataTable
          columns={['Symbol', 'Outcome', 'Net Profit %', 'Entry Price', 'Exit Price', 'Target 1', 'Stop Loss', 'Suggested Time', 'Closed At', 'Details']}
          rows={auditHistory.map((row, index) => [
            <strong key={`${row.symbol}-${index}`}>{row.symbol}</strong>,
            <span key={`${row.symbol}-status-${index}`} className={`status-badge ${row.outcome === 'Target Hit' ? 'status-good' : 'status-bad'}`}>
              {row.outcome === 'Target Hit' ? 'TARGET HIT' : 'STOPLOSS HIT'}
            </span>,
            <span key={`${row.symbol}-pnl-${index}`} className={row.profit_loss_pct >= 0 ? 'positive' : 'negative'} style={{ fontWeight: 'bold' }}>
              {row.profit_loss_pct >= 0 ? `+${row.profit_loss_pct.toFixed(2)}%` : `${row.profit_loss_pct.toFixed(2)}%`}
            </span>,
            row.entry_price ? `INR ${row.entry_price.toFixed(2)}` : '-',
            row.exit_price ? `INR ${row.exit_price.toFixed(2)}` : '-',
            row.target1 ? `INR ${row.target1.toFixed(2)}` : '-',
            row.stop_loss ? `INR ${row.stop_loss.toFixed(2)}` : '-',
            row.suggested_time || '-',
            row.archived_at ? new Date(row.archived_at).toLocaleString('en-IN') : '-',
            row.hit_details || row.trade_reason || '-',
          ])}
          emptyTitle="No completed watchlist outcomes"
          emptyBody="When a monitored stock hits its target or stoploss price, it will be automatically moved here for performance auditing."
        />
      </TerminalPanel>
    </main>
  );
}
