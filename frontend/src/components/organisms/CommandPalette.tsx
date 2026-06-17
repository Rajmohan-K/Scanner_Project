"use client";
import React, { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { BarChart3, Bell, FileText, Gauge, LineChart, Radar, Search, Settings, Star, Target, X } from 'lucide-react';

const commands = [
  { label: 'Open Dashboard', hint: 'Executive summary and opportunities', href: '/dashboard', icon: Gauge },
  { label: 'Run Scanner V20', hint: 'Profitability gate and scan controls', href: '/scan-center', icon: Radar },
  { label: 'Analyze Premarket', hint: 'Opening opportunities and validation', href: '/premarket', icon: Target },
  { label: 'Intraday Workbench', hint: 'Short-term setups and live monitor', href: '/intraday', icon: BarChart3 },
  { label: 'Swing Intelligence', hint: 'Multi-day opportunity analysis', href: '/swing', icon: LineChart },
  { label: 'Reports Library', hint: 'Saved scans and exports', href: '/reports', icon: FileText },
  { label: 'Watchlist Alerts', hint: 'Pinned stocks and alert queue', href: '/watchlist', icon: Bell },
  { label: 'Personalization', hint: 'Themes, settings, modules', href: '/settings', icon: Settings },
];

export default function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setOpen((value) => !value);
      }
      if (event.key === 'Escape') setOpen(false);
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return commands;
    return commands.filter((command) => `${command.label} ${command.hint}`.toLowerCase().includes(needle));
  }, [query]);

  function runCommand(href: string) {
    setOpen(false);
    setQuery('');
    router.push(href);
  }

  return (
    <>
      <button className="command-trigger" type="button" onClick={() => setOpen(true)}>
        <Search size={16} />
        <span>Search or command</span>
        <kbd>Ctrl K</kbd>
      </button>
      {open && (
        <div className="command-backdrop" role="presentation" onClick={() => setOpen(false)}>
          <section className="command-palette" role="dialog" aria-modal="true" aria-label="Command palette" onClick={(event) => event.stopPropagation()}>
            <header>
              <Search size={18} />
              <input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search stocks, screens, reports, workflows..." />
              <button className="icon-button" type="button" title="Close command palette" onClick={() => setOpen(false)}><X size={16} /></button>
            </header>
            <div className="command-list">
              {filtered.map(({ label, hint, href, icon: Icon }) => (
                <button key={href} type="button" onClick={() => runCommand(href)}>
                  <Icon size={18} />
                  <span><strong>{label}</strong><small>{hint}</small></span>
                  <Star size={14} />
                </button>
              ))}
              {!filtered.length && <div className="command-empty">No matching workflow found</div>}
            </div>
          </section>
        </div>
      )}
    </>
  );
}
