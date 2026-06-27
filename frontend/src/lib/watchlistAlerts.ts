import type { AlertHistoryRecord, AlertSettings } from '@/lib/api';

export const WATCHLIST_ALERT_SETTINGS_KEY = 'scanner-watchlist-alert-settings';
export const WATCHLIST_SEEN_ALERTS_KEY = 'scanner-watchlist-seen-alert-ids';
export const WATCHLIST_NOTIFIED_DESKTOP_KEY = 'scanner-watchlist-notified-desktop-ids';
export const WATCHLIST_ALERT_EVENT = 'scanner-watchlist-alert';

export const DEFAULT_WATCHLIST_ALERT_SETTINGS: AlertSettings = {
  min_profit_pct: 1.5,
  breakout_distance_pct: 2,
  breakout_volume_multiplier: 1.5,
  consecutive_candle_count: 3,
  price_move_pct_threshold: 1.5,
  half_percent_move_threshold: 0.5,
  cooldown_seconds: 900,
  monitoring_interval_seconds: 1,
  desktop_enabled: true,
  browser_alerts_enabled: true,
  volume_alerts_enabled: true,
  target_alerts_enabled: true,
  stop_loss_alerts_enabled: true,
  buy_alerts_enabled: true,
  sell_alerts_enabled: true,
  sound_enabled: true,
  telegram_enabled: false,
  watchlist_monitoring_enabled: true,
  groww_source_enabled: true,
  no_breakout_first_30_minutes: true,
  first_30_minutes_wait_until: '09:45',
  wait_until_11am_confirmation: true,
  confirmation_wait_until: '11:00',
  stop_loss_min_pct: 1,
  stop_loss_max_pct: 1.5,
  default_stop_loss_pct: 1,
  profit_booking_start_pct: 1.5,
  profit_booking_end_pct: 3,
  book_partial_quantity_pct: 50,
  gtt_plan_enabled: true,
  future_auto_trade_enabled: false,
  market_hours_only: false,
  avoid_negative_alerts: true,
  auto_add_candidates: false,
  price_surge_pct: 0.75,
};

function browserStorage() {
  return typeof window !== 'undefined' ? window.localStorage : null;
}

export function readWatchlistAlertSettings(): AlertSettings {
  const storage = browserStorage();
  if (!storage) return { ...DEFAULT_WATCHLIST_ALERT_SETTINGS };
  try {
    const stored = storage.getItem(WATCHLIST_ALERT_SETTINGS_KEY);
    return { ...DEFAULT_WATCHLIST_ALERT_SETTINGS, ...(stored ? JSON.parse(stored) : {}) };
  } catch {
    return { ...DEFAULT_WATCHLIST_ALERT_SETTINGS };
  }
}

export function storeWatchlistAlertSettings(settings: AlertSettings) {
  browserStorage()?.setItem(WATCHLIST_ALERT_SETTINGS_KEY, JSON.stringify(settings));
}

export function readSeenAlertIds(): Set<string> {
  const storage = browserStorage();
  if (!storage) return new Set();
  try {
    const stored = storage.getItem(WATCHLIST_SEEN_ALERTS_KEY);
    const rows = stored ? JSON.parse(stored) : [];
    return new Set(Array.isArray(rows) ? rows.filter(Boolean) : []);
  } catch {
    return new Set();
  }
}

export function markAlertSeen(alertId: string) {
  if (!alertId) return;
  const seen = readSeenAlertIds();
  seen.add(alertId);
  const trimmed = Array.from(seen).slice(-300);
  browserStorage()?.setItem(WATCHLIST_SEEN_ALERTS_KEY, JSON.stringify(trimmed));
}

export function markAlertsSeen(alertIds: string[]) {
  alertIds.filter(Boolean).forEach(markAlertSeen);
}

export function readNotifiedDesktopIds(): Set<string> {
  const storage = browserStorage();
  if (!storage) return new Set();
  try {
    const stored = storage.getItem(WATCHLIST_NOTIFIED_DESKTOP_KEY);
    const rows = stored ? JSON.parse(stored) : [];
    return new Set(Array.isArray(rows) ? rows.filter(Boolean) : []);
  } catch {
    return new Set();
  }
}

export function markDesktopNotified(alertId: string) {
  if (!alertId) return;
  const notified = readNotifiedDesktopIds();
  notified.add(alertId);
  browserStorage()?.setItem(WATCHLIST_NOTIFIED_DESKTOP_KEY, JSON.stringify(Array.from(notified).slice(-300)));
}

export function isDesktopNotified(alertId?: string) {
  return Boolean(alertId && readNotifiedDesktopIds().has(alertId));
}

export function playWatchlistAlertTone(severity?: string, actionOrType?: string) {
  if (typeof window === 'undefined') return;
  try {
    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
    if (!AudioContextClass) return;
    const ctx = new AudioContextClass();
    
    const playBeep = (freq: number, duration: number, delay = 0, vol = 0.035) => {
      const oscillator = ctx.createOscillator();
      const gain = ctx.createGain();
      oscillator.frequency.value = freq;
      gain.gain.value = vol;
      oscillator.connect(gain);
      gain.connect(ctx.destination);
      oscillator.start(ctx.currentTime + delay);
      oscillator.stop(ctx.currentTime + delay + duration);
    };

    const play = () => {
      const text = String(actionOrType || '').toUpperCase();
      const sev = String(severity || '').toLowerCase();

      const isBuy = text.includes('BUY') || text.includes('LONG');
      const isSell = text.includes('SELL') || text.includes('SHORT');

      if (isBuy) {
        // Rising arpeggio (C5 -> E5 -> G5 -> C6)
        playBeep(523.25, 0.10, 0.00, 0.05);
        playBeep(659.25, 0.10, 0.12, 0.05);
        playBeep(783.99, 0.10, 0.24, 0.05);
        playBeep(1046.50, 0.22, 0.36, 0.06);
      } else if (isSell) {
        // Descending warning arpeggio (C6 -> G5 -> E5 -> C5)
        playBeep(1046.50, 0.10, 0.00, 0.06);
        playBeep(783.99, 0.10, 0.12, 0.05);
        playBeep(659.25, 0.10, 0.24, 0.05);
        playBeep(523.25, 0.22, 0.36, 0.05);
      } else if (sev === 'high') {
        // Strong double beep: louder (0.05 vol), 880 Hz
        playBeep(880, 0.12, 0, 0.05);
        playBeep(880, 0.12, 0.16, 0.05);
      } else if (sev === 'medium') {
        // Medium beep: 820 Hz, 0.22 seconds
        playBeep(820, 0.22, 0, 0.04);
      } else {
        // Low/Normal beep: 740 Hz, 0.16 seconds
        playBeep(740, 0.16, 0, 0.035);
      }
    };

    if (ctx.state === 'suspended') {
      ctx.resume().then(play).catch(() => {});
    } else {
      play();
    }
  } catch {
    // Browser may block audio until user interaction.
  }
}

export function dispatchWatchlistAlert(alert: AlertHistoryRecord) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(WATCHLIST_ALERT_EVENT, { detail: alert }));
}

type ToastPush = (message: string, type?: 'info' | 'success' | 'error' | 'warning', options?: { dedupeKey?: string; desktop?: boolean }) => void;

export function notifyWatchlistAlert(
  alert: AlertHistoryRecord,
  settings: AlertSettings = readWatchlistAlertSettings(),
  toast?: { push: ToastPush },
) {
  if (!alert?.alert_id) return false;
  const seen = readSeenAlertIds();
  if (seen.has(alert.alert_id)) return false;

  markAlertSeen(alert.alert_id);
  dispatchWatchlistAlert(alert);

  const sev = String(alert.severity || '').toUpperCase();
  const isPriority = sev === 'CRITICAL' || sev === 'HIGH';

  if (!isPriority) {
    return true;
  }

  const title = `${alert.symbol}: ${alert.action || alert.alert_type}`;
  const body = alert.reason || alert.message || '';
  const toastType = (sev === 'CRITICAL' || sev === 'HIGH') ? 'success' : 'info';

  toast?.push(title, toastType, { dedupeKey: `watchlist:${alert.alert_id}`, desktop: false });

  if (settings.sound_enabled) {
    playWatchlistAlertTone(alert.severity, alert.action || alert.alert_type);
  }

  const desktopEnabled = settings.desktop_enabled !== false && alert.desktop_sent !== false;
  if (
    desktopEnabled
    && typeof window !== 'undefined'
    && 'Notification' in window
  ) {
    const requireInteraction = sev === 'HIGH' || sev === 'CRITICAL';
    
    const showNotification = () => {
      new window.Notification(`Stock Alert: ${alert.symbol}`, { 
        body: body ? `${alert.action || alert.alert_type} - ${body}` : String(alert.action || alert.alert_type),
        requireInteraction: requireInteraction,
        tag: alert.alert_id
      });
      markDesktopNotified(alert.alert_id);
    };

    if (window.Notification.permission === 'granted') {
      showNotification();
    } else if (window.Notification.permission === 'default') {
      window.Notification.requestPermission().then((permission) => {
        if (permission === 'granted') {
          showNotification();
        }
      });
    }
  }

  return true;
}

export function desktopDeliveryLabel(alert: AlertHistoryRecord) {
  if (isDesktopNotified(alert.alert_id)) return 'Notified';
  if (alert.delivery_status === 'ui_notified') return 'Notified';
  if (alert.desktop_sent === false) return 'Off';
  return 'Pending';
}
