"use client";
import { useEffect, useState } from 'react';

export type ThemeMode = 'dark' | 'light';
export type PremiumTheme =
  | 'quantum'
  | 'executive'
  | 'sapphire'
  | 'emerald'
  | 'platinum'
  | 'cyber'
  | 'midnight'
  | 'institutional';

export const premiumThemes: Array<{ id: PremiumTheme; label: string }> = [
  { id: 'quantum', label: 'Quantum Black' },
  { id: 'executive', label: 'Executive Gold' },
  { id: 'sapphire', label: 'Sapphire Elite' },
  { id: 'emerald', label: 'Emerald Wealth' },
  { id: 'platinum', label: 'Platinum Silver' },
  { id: 'cyber', label: 'Cyber Blue' },
  { id: 'midnight', label: 'Midnight Pro' },
  { id: 'institutional', label: 'Institutional Dark' },
];

export function normalizeThemeMode(value: string | undefined | null): ThemeMode {
  const normalized = String(value || '').toLowerCase();
  if (normalized === 'light') return 'light';
  if (normalized === 'dark') return 'dark';
  if (typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: light)').matches) return 'light';
  return 'dark';
}

export function premiumThemeFromAccent(value: string | undefined | null): PremiumTheme {
  const normalized = String(value || '').toLowerCase();
  if (normalized.includes('green') || normalized.includes('emerald')) return 'emerald';
  if (normalized.includes('amber') || normalized.includes('gold')) return 'executive';
  if (normalized.includes('silver') || normalized.includes('platinum')) return 'platinum';
  if (normalized.includes('blue')) return 'sapphire';
  return 'quantum';
}

export function applyThemeSettings(settings: Record<string, any>) {
  if (typeof window === 'undefined') return;
  const mode = normalizeThemeMode(settings.theme_mode);
  const premium = settings.premium_theme || premiumThemeFromAccent(settings.accent_color);
  document.documentElement.setAttribute('data-theme', mode);
  document.documentElement.setAttribute('data-premium-theme', premium);
  document.documentElement.setAttribute('data-density', settings.dense_layout === false ? 'comfortable' : 'dense');
  localStorage.setItem('theme', mode);
  localStorage.setItem('premium-theme', premium);
  localStorage.setItem('layout-density', settings.dense_layout === false ? 'comfortable' : 'dense');
  window.dispatchEvent(new CustomEvent('scanner-theme-settings', { detail: { mode, premiumTheme: premium } }));
}

export function useDarkMode() {
  const [mode, setMode] = useState<ThemeMode>(() => {
    if (typeof window === 'undefined') return 'dark';
    return (localStorage.getItem('theme') as ThemeMode) || (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
  });
  const [premiumTheme, setPremiumTheme] = useState<PremiumTheme>(() => {
    if (typeof window === 'undefined') return 'quantum';
    return (localStorage.getItem('premium-theme') as PremiumTheme) || 'quantum';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', mode);
    localStorage.setItem('theme', mode);
  }, [mode]);

  useEffect(() => {
    document.documentElement.setAttribute('data-premium-theme', premiumTheme);
    localStorage.setItem('premium-theme', premiumTheme);
  }, [premiumTheme]);

  useEffect(() => {
    function handleThemeEvent(event: Event) {
      const detail = (event as CustomEvent).detail || {};
      if (detail.mode) setMode(detail.mode);
      if (detail.premiumTheme) setPremiumTheme(detail.premiumTheme);
    }
    function handleStorage(event: StorageEvent) {
      if (event.key === 'theme' && event.newValue) setMode(normalizeThemeMode(event.newValue));
      if (event.key === 'premium-theme' && event.newValue) setPremiumTheme(event.newValue as PremiumTheme);
    }
    window.addEventListener('scanner-theme-settings', handleThemeEvent);
    window.addEventListener('storage', handleStorage);
    return () => {
      window.removeEventListener('scanner-theme-settings', handleThemeEvent);
      window.removeEventListener('storage', handleStorage);
    };
  }, []);

  function toggle() { setMode((m) => (m === 'dark' ? 'light' : 'dark')); }

  return { mode, setMode, toggle, premiumTheme, setPremiumTheme, premiumThemes };
}

export default useDarkMode;
