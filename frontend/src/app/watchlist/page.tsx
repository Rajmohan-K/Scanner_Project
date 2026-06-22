"use client";

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Bell, BellOff, History, Plus, RefreshCw, RotateCcw, Save, Settings2, ShieldCheck, Trash2 } from 'lucide-react';
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
} from '@/lib/api';
import { PageHero, TerminalPanel } from '@/components/terminal/TerminalPrimitives';
import { useToast } from '@/components/layout/ToastProvider';

const DEFAULT_ALERT_SETTINGS: Record<string, any> = {
  breakout_distance_pct: 2,
  breakout_volume_multiplier: 2,
  consecutive_candle_count: 3,
  price_move_pct_threshold: 2,
  half_percent_move_threshold: 0.5,
  cooldown_seconds: 900,
  monitoring_interval_seconds: 10,
  desktop_enabled: true,
  sound_enabled: false,
  telegram_enabled: false,
  watchlist_monitoring_enabled: true,
  no_breakout_first_30_minutes: true,
  first_30_minutes_wait_until: '09:45',
  wait_until_11am_confirmation: true,
  confirmation_wait_until: '11:00',
  stop_loss_min_pct: 1,
  stop_loss_max_pct: 1.5,
  default_stop_loss_pct: 1.2,
  profit_booking_start_pct: 4,
  profit_booking_end_pct: 5,
  book_partial_quantity_pct: 50,
  gtt_plan_enabled: true,
  future_auto_trade_enabled: false,
  market_hours_only: false,
};

const ALERT_SETTINGS_STORAGE_KEY = 'scanner-watchlist-alert-settings';

function readStoredAlertSettings() {
  if (typeof window === 'undefined') return {};
  try {
    const stored = window.localStorage.getItem(ALERT_SETTINGS_STORAGE_KEY);
    return stored ? JSON.parse(stored) : {};
  } catch {
    return {};
  }
}

function storeAlertSettings(settings: Record<string, any>) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(ALERT_SETTINGS_STORAGE_KEY, JSON.stringify(settings));
  } catch {
    // Backend persistence remains available when browser storage is blocked.
  }
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

function playSoftTone() {
  if (typeof window === 'undefined') return;
  try {
    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
    if (!AudioContextClass) return;
    const ctx = new AudioContextClass();
    const oscillator = ctx.createOscillator();
    const gain = ctx.createGain();
    oscillator.frequency.value = 740;
    gain.gain.value = 0.035;
    oscillator.connect(gain);
    gain.connect(ctx.destination);
    oscillator.start();
    oscillator.stop(ctx.currentTime + 0.16);
  } catch {
    // Browser may block audio until user interaction.
  }
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
  const [historyFilters, setHistoryFilters] = useState<Record<string, string>>({});
  const [connection, setConnection] = useState('Connecting');
  const [settingsDirty, setSettingsDirty] = useState(false);
  const settingsLoaded = useRef(false);
  const seenAlertIds = useRef<Set<string>>(new Set());

  async function load() {
    setLoading(true);
    setError('');
    try {
      const [watchlist, alertSettings] = await Promise.all([getWatchlist(), getAlertSettings()]);
      const storedSettings = readStoredAlertSettings();
      const mergedSettings = {
        ...DEFAULT_ALERT_SETTINGS,
        ...(alertSettings.settings || {}),
        ...storedSettings,
      };
      setItems(watchlist.items || []);
      setSettings(mergedSettings);
      storeAlertSettings(mergedSettings);
      const historyResponse = await getWatchlistHistory({ limit: 80 });
      setHistory(historyResponse.alerts || []);
      seenAlertIds.current = new Set((historyResponse.alerts || []).map((row) => row.alert_id));
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
        storeAlertSettings(savedSettings);
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
          const newest = alerts.find((alert: AlertHistoryRecord) => alert.alert_id && !seenAlertIds.current.has(alert.alert_id));
          alerts.forEach((alert: AlertHistoryRecord) => {
            if (alert.alert_id) seenAlertIds.current.add(alert.alert_id);
          });
          if (newest) {
            toast.push(`${newest.symbol}: ${newest.action || newest.alert_type}`, newest.severity === 'high' ? 'success' : 'info');
            if (settings.sound_enabled) playSoftTone();
            if (settings.desktop_enabled !== false && typeof window !== 'undefined' && 'Notification' in window && Notification.permission === 'granted') {
              new Notification(`Stock Alert: ${newest.symbol}`, { body: `${newest.action || newest.alert_type} - ${newest.reason || newest.message || ''}` });
            }
          }
        }
      } catch {
        setConnection('Stream error');
      }
    });
    return () => source.close();
  }, [settings.desktop_enabled, settings.sound_enabled, toast]);

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
      setItems((current) => [response.item, ...current.filter((item) => item.symbol !== response.item.symbol)]);
      toast.push(`${response.item.symbol} added to watchlist monitor`, 'success');
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

  async function saveGlobalSettings() {
    storeAlertSettings(settings);
    try {
      const response = await saveAlertSettings(settings);
      const savedSettings = { ...DEFAULT_ALERT_SETTINGS, ...(response.settings || settings) };
      setSettings(savedSettings);
      storeAlertSettings(savedSettings);
      setSettingsDirty(false);
      toast.push('Alert settings saved', 'success');
    } catch (err: any) {
      toast.push(`${err?.message || 'Unable to sync alert settings to backend.'} Changes remain saved in this browser.`, 'error');
    }
  }

  function updateGlobalSettings(patch: Record<string, any>) {
    setSettings((current) => {
      const nextSettings = { ...current, ...patch };
      storeAlertSettings(nextSettings);
      return nextSettings;
    });
    setSettingsDirty(true);
  }

  function resetDefaults() {
    const defaults = { ...DEFAULT_ALERT_SETTINGS };
    setSettings(defaults);
    storeAlertSettings(defaults);
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
        title="Live Watchlist Trade Alerts"
        description="Backend-monitored symbols with strict time, volume, SL, GTT, profit-booking, desktop, and Telegram alert readiness. Manual confirmation required; auto trading disabled."
        actions={<>
          <button className="btn-secondary" type="button" onClick={load}><RefreshCw size={16} /> Refresh</button>
          <button className="btn-secondary" type="button" onClick={requestDesktopPermission}><Bell size={16} /> Browser Alerts</button>
          <button className="btn-secondary" type="button" onClick={resetDefaults}><RotateCcw size={16} /> Reset Defaults</button>
          <button className="btn-primary" type="button" onClick={saveGlobalSettings}><Save size={16} /> Save Alert Settings</button>
        </>}
        metrics={[
          { label: 'Connection', value: connection, tone: connection === 'Live' ? 'good' : 'warn' },
          { label: 'Monitored', value: String(stats.monitored) },
          { label: 'Alerts Enabled', value: String(stats.alerts) },
          { label: 'Trade Ready', value: String(stats.tradeReady), tone: stats.tradeReady ? 'good' : 'warn' },
          { label: 'Waiting', value: String(stats.wait), tone: stats.wait ? 'warn' : 'good' },
        ]}
      />

      <TerminalPanel eyebrow="Add Stock" title="Custom Stock Monitor">
        <div className="watchlist-add-row">
          <input value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} placeholder="RELIANCE, TCS, MTARTECH" onKeyDown={(event) => { if (event.key === 'Enter') addSymbol(); }} />
          <button className="btn-primary" type="button" onClick={addSymbol}><Plus size={16} /> Add Stock</button>
        </div>
        <div className="settings-grid compact-settings-grid">
          {[
            ['breakout_distance_pct', 'Breakout Distance %', 'Near resistance alert zone, suggested 2%.'],
            ['breakout_volume_multiplier', 'Volume Multiplier', 'BUY confirmation volume, default 2x.'],
            ['consecutive_candle_count', 'Candle Count', 'Consecutive candle alert count, suggested 3.'],
            ['price_move_pct_threshold', 'Price Move %', 'Single-candle price movement alert, suggested 2%.'],
            ['half_percent_move_threshold', 'Half % Move', 'Alert from last alert price, default 0.5%.'],
            ['stop_loss_min_pct', 'SL Min %', 'Minimum strict stop loss, default 1%.'],
            ['stop_loss_max_pct', 'SL Max %', 'Maximum allowed risk, default 1.5%.'],
            ['default_stop_loss_pct', 'Default SL %', 'GTT stop loss default, suggested 1.2%.'],
            ['profit_booking_start_pct', 'Book Start %', 'Start 50% profit booking, default 4%.'],
            ['profit_booking_end_pct', 'Book End %', 'Profit booking zone end, default 5%.'],
            ['book_partial_quantity_pct', 'Partial Qty %', 'Suggested partial exit quantity, default 50%.'],
            ['cooldown_seconds', 'Cooldown Seconds', 'Duplicate alert cooldown, suggested 900 seconds.'],
            ['monitoring_interval_seconds', 'Monitor Interval', 'Backend monitor cycle, suggested 10 seconds.'],
          ].map(([key, label, hint]) => (
            <label key={key} className="field-card">
              <span>{label}</span>
              <input type="number" value={settings[key] ?? ''} onChange={(event) => updateGlobalSettings({ [key]: Number(event.target.value) })} />
              <small>{hint}</small>
            </label>
          ))}
          <label className="field-card">
            <span>First Window Ends</span>
            <input type="time" value={settings.first_30_minutes_wait_until ?? '09:45'} onChange={(event) => updateGlobalSettings({ first_30_minutes_wait_until: event.target.value })} />
            <small>No breakout BUY before this time.</small>
          </label>
          <label className="field-card">
            <span>Confirm After</span>
            <input type="time" value={settings.confirmation_wait_until ?? '11:00'} onChange={(event) => updateGlobalSettings({ confirmation_wait_until: event.target.value })} />
            <small>Momentum waits until this confirmation time.</small>
          </label>
          <label className="toggle-card"><input type="checkbox" checked={settings.watchlist_monitoring_enabled !== false} onChange={(event) => updateGlobalSettings({ watchlist_monitoring_enabled: event.target.checked })} /> Enable Monitoring</label>
          <label className="toggle-card"><input type="checkbox" checked={settings.no_breakout_first_30_minutes !== false} onChange={(event) => updateGlobalSettings({ no_breakout_first_30_minutes: event.target.checked })} /> No BUY First 30m</label>
          <label className="toggle-card"><input type="checkbox" checked={settings.wait_until_11am_confirmation !== false} onChange={(event) => updateGlobalSettings({ wait_until_11am_confirmation: event.target.checked })} /> Wait Until 11 AM</label>
          <label className="toggle-card"><input type="checkbox" checked={settings.gtt_plan_enabled !== false} onChange={(event) => updateGlobalSettings({ gtt_plan_enabled: event.target.checked })} /> GTT Plan Values</label>
          <label className="toggle-card"><input type="checkbox" checked={Boolean(settings.market_hours_only)} onChange={(event) => updateGlobalSettings({ market_hours_only: event.target.checked })} /> Market Hours Only</label>
          <label className="toggle-card"><input type="checkbox" checked={settings.desktop_enabled !== false} onChange={(event) => updateGlobalSettings({ desktop_enabled: event.target.checked })} /> Desktop Alerts</label>
          <label className="toggle-card"><input type="checkbox" checked={Boolean(settings.sound_enabled)} onChange={(event) => updateGlobalSettings({ sound_enabled: event.target.checked })} /> Alert Sound</label>
          <label className="toggle-card"><input type="checkbox" checked={Boolean(settings.telegram_enabled)} onChange={(event) => updateGlobalSettings({ telegram_enabled: event.target.checked })} /> Telegram Alerts</label>
          <label className="toggle-card disabled-toggle"><input type="checkbox" checked={false} disabled /> Future Auto Buy/Sell Disabled</label>
        </div>
        <div className="status-banner info"><ShieldCheck size={16} /> Manual confirmation required. Auto buy/sell is disabled; use Groww GTT manually for Target/SL.</div>
      </TerminalPanel>

      <TerminalPanel eyebrow="Live Table" title="Watched Stocks">
        {error && <div className="status-banner danger">{error}<button type="button" onClick={load}>Retry</button></div>}
        {loading ? (
          <div className="empty-state">Loading backend watchlist...</div>
        ) : items.length ? (
          <div className="terminal-table watchlist-monitor-table">
            <div className="terminal-table-head">
              {['Symbol', 'Company', 'Price', 'Change %', 'Vol vs Avg', 'Breakout', 'Distance', 'Status', 'Readiness', 'Action', 'Entry', 'SL', 'Target 1', 'Target 2', 'Target 3', 'GTT Plan', 'Profit Booking', 'Last Alert', 'Last Alert Price', 'Checked', 'Alert Enabled', 'Actions'].map((heading) => <span key={heading}>{heading}</span>)}
            </div>
            {items.map((item) => {
              const snap = item.snapshot || {};
              return (
                <article key={item.symbol} className="terminal-table-row watchlist-monitor-row" onClick={() => setSelected(item)}>
                  <strong>{item.symbol}<small>{item.company_name || '-'}</small></strong>
                  <span>{snap.company_name || item.company_name || '-'}</span>
                  <span>{formatCurrency(snap.current_price)}</span>
                  <span className={Number(snap.price_change_pct) >= 0 ? 'positive' : 'negative'}>{formatNumber(snap.price_change_pct)}%</span>
                  <span>{formatNumber(snap.volume_spike)}x</span>
                  <span>{formatNumber(snap.breakout_level)}</span>
                  <span>{formatNumber(snap.distance_to_breakout_pct)}%</span>
                  <span className={`pill pill-${statusTone(snap.current_status)}`}>{snap.current_status || 'Checking'}</span>
                  <span className={`pill pill-${statusTone(snap.trade_readiness)}`}>{snap.trade_readiness || 'Not Ready'}</span>
                  <span className={`pill pill-${actionTone(snap.action)}`}>{snap.action || 'WATCH'}</span>
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
                    <button className="icon-button" title="Toggle monitoring" type="button" onClick={(event) => { event.stopPropagation(); patchItem(item, { monitoring_enabled: item.monitoring_enabled === false }); }}>
                      {item.monitoring_enabled === false ? <BellOff size={15} /> : <Bell size={15} />}
                    </button>
                    <button className="icon-button" title="Remove" type="button" onClick={(event) => { event.stopPropagation(); removeSymbol(item); }}><Trash2 size={15} /></button>
                  </span>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="empty-state">Add a stock to start backend watchlist monitoring.</div>
        )}
      </TerminalPanel>

      {selected && (
        <TerminalPanel eyebrow="Symbol Settings" title={`${selected.symbol} Alert Rules`}>
          <div className="selected-stock-panel">
            <p>{selected.snapshot?.trade_reason || selected.snapshot?.reason || 'Backend analysis will appear after the next monitor cycle.'}</p>
            <div className="gtt-summary-grid">
              {[
                ['Readiness', selected.snapshot?.trade_readiness],
                ['Action', selected.snapshot?.action],
                ['Time Rule', selected.snapshot?.time_rule_status],
                ['Entry', formatCurrency(selected.snapshot?.entry)],
                ['SL', formatCurrency(selected.snapshot?.stop_loss)],
                ['Target 1', formatCurrency(selected.snapshot?.target1)],
                ['Target 2', formatCurrency(selected.snapshot?.target2)],
                ['Target 3', formatCurrency(selected.snapshot?.target3)],
                ['Risk %', selected.snapshot?.risk_percent ? `${formatNumber(selected.snapshot.risk_percent)}%` : '-'],
                ['Volume Confirmed', selected.snapshot?.volume_confirmed ? 'Yes' : 'No'],
                ['Manual GTT', selected.snapshot?.gtt_plan?.note || 'Use Groww GTT manually for Target/SL'],
                ['Auto Trading', 'Disabled'],
              ].map(([label, value]) => (
                <span key={label}><small>{label}</small><strong>{value || '-'}</strong></span>
              ))}
            </div>
            <div className="settings-grid compact-settings-grid">
              {[
                ['custom_breakout_price', 'Custom Breakout'],
                ['custom_support', 'Custom Support'],
                ['custom_resistance', 'Custom Resistance'],
                ['custom_price_up_pct', 'Price Up %'],
                ['custom_price_down_pct', 'Price Down %'],
                ['custom_candle_count', 'Candle Count'],
                ['quantity_placeholder', 'Qty Placeholder'],
                ['risk_amount_placeholder', 'Risk Amount'],
              ].map(([key, label]) => (
                <label key={key} className="field-card">
                  <span>{label}</span>
                  <input type={key.includes('placeholder') ? 'text' : 'number'} defaultValue={(selected as any)[key] || ''} onBlur={(event) => patchItem(selected, { [key]: key.includes('placeholder') ? event.target.value : Number(event.target.value) } as any)} />
                </label>
              ))}
              <label className="toggle-card"><input type="checkbox" checked={selected.alerts_enabled !== false} onChange={(event) => patchItem(selected, { alerts_enabled: event.target.checked })} /> Alerts</label>
              <label className="toggle-card"><input type="checkbox" checked={Boolean(selected.telegram_enabled)} onChange={(event) => patchItem(selected, { telegram_enabled: event.target.checked })} /> Telegram</label>
              <label className="toggle-card"><input type="checkbox" checked={selected.desktop_enabled !== false} onChange={(event) => patchItem(selected, { desktop_enabled: event.target.checked })} /> Desktop</label>
            </div>
            <button className="btn-secondary" type="button" onClick={() => setSelected(null)}><Settings2 size={15} /> Close Settings</button>
          </div>
        </TerminalPanel>
      )}

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
                <span>{alert.desktop_sent ? 'Ready' : 'No'}</span>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-state">No watchlist alerts yet. Alerts will appear after backend rules trigger.</div>
        )}
      </TerminalPanel>
    </main>
  );
}
