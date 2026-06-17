"use client";
import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { Download, History, RotateCcw, Save, Upload } from 'lucide-react';
import { getSettings, saveSettings } from '@/lib/api';
import { useToast } from '@/components/layout/ToastProvider';
import { setSettings, updateSetting } from '@/state/settingsSlice';
import { RootState } from '@/state/store';
import { PageHero, TerminalPanel } from '@/components/terminal/TerminalPrimitives';
import { settingsSections } from '@/lib/terminalData';
import { applyThemeSettings, premiumThemes } from '@/hooks/useDarkMode';

const sectionFields: Record<string, Array<{ key: string; label: string; type: 'checkbox' | 'number' | 'select' | 'text'; options?: string[]; value: any }>> = {
  'Premarket Configuration': [
    { key: 'premarket_enabled', label: 'Enable Premarket Scan', type: 'checkbox', value: true },
    { key: 'premarket_gap_threshold', label: 'Gap Threshold %', type: 'number', value: 1.5 },
    { key: 'premarket_volume_multiplier', label: 'Volume Multiplier', type: 'number', value: 2 },
    { key: 'premarket_news_required', label: 'Require News Confirmation', type: 'checkbox', value: false },
  ],
  'Intraday Configuration': [
    { key: 'intraday_enabled', label: 'Enable Intraday Scan', type: 'checkbox', value: true },
    { key: 'intraday_interval', label: 'Primary Interval', type: 'select', options: ['5m', '15m', '1h'], value: '15m' },
    { key: 'intraday_vwap_required', label: 'Require VWAP Confirmation', type: 'checkbox', value: true },
    { key: 'intraday_max_risk_score', label: 'Max Risk Score', type: 'number', value: 50 },
  ],
  'Swing Configuration': [
    { key: 'swing_enabled', label: 'Enable Swing Scan', type: 'checkbox', value: true },
    { key: 'swing_period', label: 'Lookback Period', type: 'select', options: ['3mo', '6mo', '1y', '2y'], value: '1y' },
    { key: 'swing_min_rr', label: 'Minimum R:R', type: 'number', value: 2 },
    { key: 'swing_review_cadence', label: 'Review Cadence', type: 'select', options: ['Daily', 'Every 2 Days', 'Weekly'], value: 'Daily' },
  ],
  'Watchlist Configuration': [
    { key: 'watchlist_alerts', label: 'Enable Alerts', type: 'checkbox', value: true },
    { key: 'watchlist_max_symbols', label: 'Max Symbols', type: 'number', value: 100 },
    { key: 'watchlist_auto_pin_breakouts', label: 'Auto Pin Breakouts', type: 'checkbox', value: false },
  ],
  'Custom Scan Configuration': [
    { key: 'custom_candidate_pool', label: 'Screened Pool', type: 'number', value: 97 },
    { key: 'custom_validation_pool', label: 'Selected Pool', type: 'number', value: 35 },
    { key: 'custom_final_pool', label: 'Final Score Pool', type: 'number', value: 10 },
    { key: 'custom_workers', label: 'Workers', type: 'number', value: 5 },
  ],
  'ML Model Configuration': [
    { key: 'ml_threshold', label: 'ML Confidence Threshold', type: 'number', value: 78 },
    { key: 'ml_walk_forward', label: 'Enable Walk Forward', type: 'checkbox', value: true },
    { key: 'ml_optimization', label: 'Enable Optimization', type: 'checkbox', value: true },
  ],
  'Technical Analysis Configuration': [
    { key: 'technical_weight', label: 'Technical Weight', type: 'number', value: 35 },
    { key: 'technical_require_trend', label: 'Require Trend Alignment', type: 'checkbox', value: true },
    { key: 'technical_breakout_weight', label: 'Breakout Weight', type: 'number', value: 15 },
  ],
  'Fundamental Analysis Configuration': [
    { key: 'fundamental_weight', label: 'Fundamental Weight', type: 'number', value: 25 },
    { key: 'fundamental_max_pe', label: 'Max PE', type: 'number', value: 60 },
    { key: 'fundamental_require_low_debt', label: 'Prefer Low Debt', type: 'checkbox', value: true },
  ],
  'Notification Configuration': [
    { key: 'notify_telegram', label: 'Telegram Alerts', type: 'checkbox', value: false },
    { key: 'telegram_category', label: 'Telegram Category', type: 'text', value: 'Premarket' },
    { key: 'notify_scan_complete', label: 'Notify On Scan Complete', type: 'checkbox', value: true },
  ],
  'Data Feed Configuration': [
    { key: 'market_refresh_seconds', label: 'Market Refresh Seconds', type: 'number', value: 5 },
    { key: 'feed_provider', label: 'Feed Provider', type: 'select', options: ['yfinance', 'cached-yfinance'], value: 'yfinance' },
    { key: 'ignore_dead_proxy', label: 'Ignore Dead Local Proxy', type: 'checkbox', value: true },
  ],
  'API Configuration': [
    { key: 'api_timeout_seconds', label: 'API Timeout Seconds', type: 'number', value: 15 },
    { key: 'backend_url', label: 'Backend URL', type: 'text', value: 'http://127.0.0.1:5000' },
    { key: 'cors_enabled', label: 'CORS Enabled', type: 'checkbox', value: true },
  ],
  'User Preferences': [
    { key: 'default_page', label: 'Default Page', type: 'select', options: ['Dashboard', 'Scan Center', 'Reports'], value: 'Dashboard' },
    { key: 'compact_tables', label: 'Compact Tables', type: 'checkbox', value: true },
    { key: 'auto_refresh', label: 'Auto Refresh', type: 'checkbox', value: true },
  ],
  'Theme Settings': [
    { key: 'theme_mode', label: 'Mode', type: 'select', options: ['System', 'Dark', 'Light'], value: 'Dark' },
    { key: 'accent_color', label: 'Accent Color', type: 'select', options: ['Blue', 'Green', 'Amber'], value: 'Blue' },
    { key: 'premium_theme', label: 'Premium Theme', type: 'select', options: premiumThemes.map((theme) => theme.id), value: 'quantum' },
    { key: 'dense_layout', label: 'Dense Layout', type: 'checkbox', value: true },
  ],
};

function defaultSettings() {
  return Object.fromEntries(
    Object.values(sectionFields)
      .flat()
      .map((field) => [field.key, field.value])
  );
}

export default function SettingsPage() {
  const dispatch = useDispatch();
  const toast = useToast();
  const savedSettings = useSelector((state: RootState) => state.settings.data);
  const [settings, setSettingsState] = useState<any>(savedSettings || {});
  const [lastSavedSettings, setLastSavedSettings] = useState<any>(savedSettings || {});
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState(settingsSections[0]);

  useEffect(() => {
    async function load() {
      try {
        const s = await getSettings();
        const loaded = s?.settings || {};
        const merged = { ...defaultSettings(), ...loaded };
        dispatch(setSettings(merged));
        setSettingsState(merged);
        setLastSavedSettings(merged);
        applyThemeSettings(merged);
      } catch (err) {
        toast?.push('Unable to load settings; using editable defaults', 'warning');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [dispatch, toast]);

  async function handleSave() {
    try {
      await saveSettings(settings);
      dispatch(setSettings(settings));
      setLastSavedSettings(settings);
      applyThemeSettings(settings);
      toast?.push('Settings saved successfully', 'success');
    } catch (err) {
      toast?.push('Unable to save settings', 'error');
    }
  }

  function handleChange(key: string, value: any) {
    const next = { ...settings, [key]: value };
    setSettingsState(next);
    dispatch(updateSetting({ key, value }));
    if (['theme_mode', 'accent_color', 'premium_theme', 'dense_layout'].includes(key)) {
      applyThemeSettings(next);
    }
  }

  function handleExport() {
    const blob = new Blob([JSON.stringify(settings, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `scanner-settings-${Date.now()}.json`;
    link.click();
    URL.revokeObjectURL(url);
    toast?.push('Settings exported', 'success');
  }

  async function handleResetDefaults() {
    const next = defaultSettings();
    setSettingsState(next);
    dispatch(setSettings(next));
    applyThemeSettings(next);
    await saveSettings(next);
    setLastSavedSettings(next);
    toast?.push('Default settings restored', 'success');
  }

  function handleRollback() {
    setSettingsState(lastSavedSettings);
    dispatch(setSettings(lastSavedSettings));
    applyThemeSettings(lastSavedSettings);
    toast?.push('Rolled back to last saved settings', 'success');
  }

  function renderField(field: { key: string; label: string; type: 'checkbox' | 'number' | 'select' | 'text'; options?: string[]; value: any }) {
    const value = settings[field.key] ?? field.value;
    if (field.type === 'checkbox') {
      return <label key={field.key} className="field field--inline"><span>{field.label}</span><input type="checkbox" checked={Boolean(value)} onChange={(event) => handleChange(field.key, event.target.checked)} /></label>;
    }
    if (field.type === 'select') {
      return <label key={field.key} className="field"><span>{field.label}</span><select value={value} onChange={(event) => handleChange(field.key, event.target.value)}>{field.options?.map((option) => <option key={option}>{option}</option>)}</select></label>;
    }
    return <label key={field.key} className="field"><span>{field.label}</span><input type={field.type} value={value} onChange={(event) => handleChange(field.key, field.type === 'number' ? Number(event.target.value) : event.target.value)} /></label>;
  }

  return (
    <main>
      <PageHero
        eyebrow="Settings"
        title="Configuration Console"
        description="Category-based controls for scan modules, scoring weights, model thresholds, feed/API behavior, notifications, risk, and themes."
        actions={<><button className="btn-primary" onClick={handleSave}><Save size={16} /> Save Configuration</button><button className="btn-secondary"><History size={16} /> Version History</button></>}
        metrics={[
          { label: 'Sections', value: String(settingsSections.length) },
          { label: 'Autosave', value: settings.auto_refresh ? 'On' : 'Off' },
          { label: 'Status', value: loading ? 'Loading' : 'Ready', tone: loading ? 'warn' : 'good' },
        ]}
      />

      <div className="settings-layout">
        <aside className="settings-nav">
          {settingsSections.map((section) => (
            <button key={section} className={active === section ? 'active' : ''} onClick={() => setActive(section)}>{section}</button>
          ))}
        </aside>
        <TerminalPanel eyebrow="Configuration" title={active}>
          <div className="form-grid">
            {(sectionFields[active] || sectionFields['Custom Scan Configuration']).map(renderField)}
          </div>
          <div className="terminal-actions">
            <label className="btn-secondary settings-import-button"><Upload size={15} /> Import<input type="file" accept="application/json" onChange={async (event) => {
              const file = event.target.files?.[0];
              if (!file) return;
              try {
                const imported = JSON.parse(await file.text());
                const next = { ...defaultSettings(), ...imported };
                setSettingsState(next);
                dispatch(setSettings(next));
                applyThemeSettings(next);
                toast?.push('Settings imported. Save configuration to persist.', 'success');
              } catch {
                toast?.push('Invalid settings file', 'error');
              } finally {
                event.target.value = '';
              }
            }} /></label>
            <button className="btn-secondary" type="button" onClick={handleExport}><Download size={15} /> Export</button>
            <button className="btn-secondary" type="button" onClick={handleResetDefaults}><RotateCcw size={15} /> Reset Defaults</button>
            <button className="btn-secondary" type="button" onClick={handleRollback}>Rollback</button>
          </div>
        </TerminalPanel>
      </div>
    </main>
  );
}
