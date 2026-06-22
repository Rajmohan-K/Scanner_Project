"use client";
import React, { useEffect, useMemo, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { BarChart3, CheckCircle2, Download, Play, RefreshCw, Target, TrendingUp } from 'lucide-react';
import { extractStockRows, getActiveScans, getDedicatedScanLatest, getLatestScanWithResults, getScanStatus, getV20Quote, runDedicatedScan, startScan } from '@/lib/api';
import { setTopStocks } from '@/state/dashboardSlice';
import { RootState } from '@/state/store';
import { useRealtime } from '@/hooks/useRealtime';
import { useToast } from '@/components/layout/ToastProvider';
import StockGrid from '@/components/molecules/LazyStockGrid';
import { analysisModules } from '@/lib/terminalData';
import { DataTable, MetricTile, PageHero, ProgressLine, TerminalPanel, Toolbar } from '@/components/terminal/TerminalPrimitives';

export default function PremarketPage() {
  const dispatch = useDispatch();
  const toast = useToast();
  const topStocks = useSelector((state: RootState) => state.dashboard.topStocks);
  const [universe, setUniverse] = useState('Full NSE Universe');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [displayLimit, setDisplayLimit] = useState(10);
  const [activeScans, setActiveScans] = useState<any[]>([]);
  const [activeScanId, setActiveScanId] = useState<string | null>(null);
  const [activeStatus, setActiveStatus] = useState<any>(null);
  const [openPayload, setOpenPayload] = useState<any>(null);
  const [openQuery, setOpenQuery] = useState('');
  const [openLoading, setOpenLoading] = useState(false);
  const [openError, setOpenError] = useState('');
  const [openAutoRefresh, setOpenAutoRefresh] = useState(true);
  const topStocksRef = React.useRef<any[]>([]);
  const latestLoadInFlightRef = React.useRef(false);
  const activeScanInFlightRef = React.useRef(false);
  const openLoadInFlightRef = React.useRef(false);
  const activeScanFailuresRef = React.useRef(0);
  const activeStatusFailuresRef = React.useRef(0);
  const visibleQuotesRefreshingRef = React.useRef(false);
  const [filters, setFilters] = useState({
    minGap: '>= 1%',
    minVolume: '>= 2x avg',
    news: 'Preferred',
    minMl: '>= 55',
    maxRisk: '<= 55',
    targetPlan: 'T1 1R / T2 2R',
    stopMethod: 'Opening range / swing low-high',
  });

  useEffect(() => {
    async function loadLatest() {
      if (latestLoadInFlightRef.current) return;
      latestLoadInFlightRef.current = true;
      try {
        const data = await getLatestScanWithResults();
        dispatch(setTopStocks(data.rows));
      } catch {
        // Keep last visible premarket rows while scan data is refreshing.
      } finally {
        latestLoadInFlightRef.current = false;
      }
    }
    loadLatest();
    const timer = window.setInterval(loadLatest, 3000);
    return () => window.clearInterval(timer);
  }, [dispatch]);

  useEffect(() => {
    async function loadActiveScans() {
      if (activeScanInFlightRef.current) return;
      activeScanInFlightRef.current = true;
      try {
        const data = await getActiveScans();
        activeScanFailuresRef.current = 0;
        const rows = data.active_scans || data.scans || [];
        const premarketRows = rows.filter((scan: any) => /premarket/i.test(`${scan.scan_type} ${scan.payload?.scan_mode}`));
        setActiveScans(premarketRows);
        setLoading(premarketRows.length > 0);
        if (premarketRows[0]) {
          setActiveScanId(premarketRows[0].scan_id);
          setActiveStatus(premarketRows[0]);
        } else if (!activeScanId) {
          setActiveStatus(null);
        }
      } catch {
        activeScanFailuresRef.current += 1;
      } finally {
        activeScanInFlightRef.current = false;
      }
    }
    loadActiveScans();
    const timer = window.setInterval(loadActiveScans, 2500);
    return () => window.clearInterval(timer);
  }, [activeScanId]);

  async function loadOpenConfirmation(silent = false) {
    if (openLoadInFlightRef.current) return;
    openLoadInFlightRef.current = true;
    if (!silent) setOpenLoading(true);
    setOpenError('');
    try {
      setOpenPayload(await getDedicatedScanLatest('open-confirmation'));
    } catch (err: any) {
      setOpenError(err?.message || 'Unable to load 9:08 open confirmation results');
    } finally {
      setOpenLoading(false);
      openLoadInFlightRef.current = false;
    }
  }

  useEffect(() => {
    loadOpenConfirmation();
  }, []);

  useEffect(() => {
    if (!openAutoRefresh) return undefined;
    const timer = window.setInterval(() => loadOpenConfirmation(true), 3000);
    return () => window.clearInterval(timer);
  }, [openAutoRefresh]);

  async function handleStartScan() {
    setLoading(true);
    try {
      const result = await startScan({
        scan_mode: 'premarket',
        auto_nse_universe: universe.includes('Full'),
        period: '5d',
        interval: '5m',
        top_n: 20,
        candidate_pool: 180,
        validation_pool: 35,
        strict_shortlist: true,
        min_expected_return_pct: 5,
        min_ml_probability: 62,
        min_risk_reward: 1.8,
        max_stop_distance_pct: 5,
        min_data_reliability_score: 35,
        min_profitability_score: 18,
        market_open_analysis: true,
        options: filters,
      });
      toast?.push(`Premarket scan started: ${result.scan_id}`, 'success');
      setActiveScanId(result.scan_id);
      setActiveStatus(result);
      setActiveScans((current) => [result, ...current]);
    } catch (err) {
      dispatch(setTopStocks([]));
      toast?.push('Backend scan start failed', 'error');
      setLoading(false);
    }
  }

  async function handleOpenConfirmation() {
    setOpenLoading(true);
    try {
      await runDedicatedScan('open-confirmation', { market_open_time: '09:08' });
      toast?.push('9:08 open confirmation started from latest premarket candidates', 'success');
      await loadOpenConfirmation(true);
    } catch (err: any) {
      const message = err?.message || 'Open confirmation scan failed';
      setOpenError(message);
      toast?.push(message, 'error');
    } finally {
      setOpenLoading(false);
    }
  }

  useEffect(() => {
    if (!activeScanId) return;
    let cancelled = false;

    async function pollScan() {
      try {
        const status = await getScanStatus(activeScanId as string);
        if (cancelled) return;
        activeStatusFailuresRef.current = 0;
        setActiveStatus(status);
        if (status.status === 'completed') {
          dispatch(setTopStocks(extractStockRows(status)));
          toast?.push('Premarket scan completed with backend results', 'success');
          setActiveScanId(null);
          setLoading(false);
        }
        if (status.status === 'error' || status.status === 'cancelled') {
          toast?.push(status.result?.message || status.message || `Scan ${status.status}`, 'error');
          setActiveScanId(null);
          setLoading(false);
        }
      } catch {
        activeStatusFailuresRef.current += 1;
        if (!cancelled && activeStatusFailuresRef.current === 3) {
          toast?.push('Premarket scan status is delayed; keeping last known state', 'warning');
        }
      }
    }

    pollScan();
    const timer = window.setInterval(pollScan, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [activeScanId, dispatch, toast]);

  useRealtime((msg) => {
    if (msg?.type === 'premarket-qualified') dispatch(setTopStocks(msg.payload || []));
  });

  const stocks = topStocks;
  const filtered = useMemo(() => stocks.filter((stock: any) => `${stock.symbol} ${stock.stock} ${stock.sector}`.toLowerCase().includes(query.toLowerCase())), [stocks, query]);
  const visibleStocks = useMemo(() => filtered.slice(0, displayLimit), [filtered, displayLimit]);
  const openRows = useMemo(
    () => extractStockRows(openPayload, { actionableOnly: false, horizon: 'intraday' })
      .filter((row: any) => `${row.symbol || row.stock || ''} ${row.sector || ''} ${row.reason || row.trade_reason || ''}`.toLowerCase().includes(openQuery.toLowerCase())),
    [openPayload, openQuery],
  );
  const visibleQuoteSymbols = useMemo(() => visibleStocks.slice(0, Math.min(displayLimit, 25)).map((stock: any) => stock.symbol || stock.stock).filter(Boolean), [visibleStocks, displayLimit]);
  const visibleQuoteSymbolsKey = visibleQuoteSymbols.join('|');
  useEffect(() => {
    topStocksRef.current = topStocks;
  }, [topStocks]);
  useEffect(() => {
    if (!visibleQuoteSymbols.length) return;
    async function refreshVisibleQuotes() {
      if (visibleQuotesRefreshingRef.current) return;
      visibleQuotesRefreshingRef.current = true;
      try {
        const quotes = await Promise.all(visibleQuoteSymbols.map(async (symbol) => {
          try {
            const payload = await getV20Quote(symbol);
            const quote = payload?.quote || {};
            const live = Number(quote.current_price ?? quote.regularMarketPrice ?? quote.price ?? 0);
            const previous = Number(quote.previous_close || 0);
            return { symbol, live: Number.isFinite(live) && live > 0 ? Math.round(live * 100) / 100 : undefined, change: previous && live ? Math.round(((live - previous) / previous) * 10000) / 100 : undefined };
          } catch {
            return { symbol };
          }
        }));
        const bySymbol = new Map(quotes.filter((item) => item.live !== undefined).map((item) => [item.symbol, item]));
        if (!bySymbol.size) return;
        dispatch(setTopStocks(topStocksRef.current.map((stock: any) => {
          const symbol = stock.symbol || stock.stock;
          const item = bySymbol.get(symbol);
          return item ? { ...stock, live_price: item.live, current_price: item.live, change_pct: item.change ?? stock.change_pct, last_updated: new Date().toISOString() } : stock;
        })));
      } finally {
        visibleQuotesRefreshingRef.current = false;
      }
    }
    refreshVisibleQuotes();
    const timer = window.setInterval(refreshVisibleQuotes, 1000);
    return () => window.clearInterval(timer);
  }, [dispatch, visibleQuoteSymbolsKey]);

  function exportOpenConfirmationCsv() {
    const headers = ['Symbol', 'Open Price', 'Price 9:08', 'Gap Hold', 'VWAP', 'Volume', 'Confirmation Score', 'Decision', 'Reason'];
    const lines = [headers.join(',')].concat(openRows.map((row: any) => {
      const validation = row.market_open_validation || {};
      const analysis = row.market_open_analysis || {};
      const reason = String(row.reason || row.trade_reason || row.quality_filter_reasons || '').replace(/"/g, '""');
      return [
        row.symbol || row.stock || '',
        analysis.market_open_price || row.open || '',
        analysis.target_time_price || row.live_price || '',
        validation.gap_hold_percent || '',
        validation.vwap_status || '',
        row.volume_strength || '',
        validation.market_open_confirmation_score || row.ml_probability || '',
        row.action || row.premarket_action || row.signal || '',
        `"${reason}"`,
      ].join(',');
    }));
    const url = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'open-confirmation.csv';
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main>
      <PageHero
        eyebrow="Premarket Pipeline"
        title="Premarket + Open Confirmation Desk"
        description="Run pre-open gap, volume, news, sector rotation, derivatives, and ML analysis, then validate the same shortlist at 9:08 without rescanning the full market."
        actions={<><button className="btn-primary" onClick={handleStartScan}><Play size={16} /> {loading ? 'Start Another Premarket Scan' : 'Start Premarket Scan'}</button><button className="btn-secondary" onClick={handleOpenConfirmation} disabled={openLoading}><CheckCircle2 size={16} /> Run 9:08 Confirmation</button></>}
        metrics={[
          { label: 'Universe', value: universe.replace(' Universe', '') },
          { label: 'Modules', value: String(analysisModules.length), tone: 'good' },
          { label: 'Active Premarket', value: String(activeScans.length), tone: activeScans.length ? 'good' : 'warn' },
          { label: 'Confirmed Open', value: String(openRows.length), tone: openRows.length ? 'good' : 'warn' },
        ]}
      />

      <div className="terminal-grid terminal-grid--split">
        <TerminalPanel eyebrow="Scan Inputs" title="Universe and Analysis Modules">
          <div className="control-grid">
            {['Full NSE Universe', 'Custom Stocks', 'Watchlist Stocks', 'Selected Sectors', 'Selected Industries'].map((item) => (
              <button key={item} className={universe === item ? 'choice-card active' : 'choice-card'} onClick={() => setUniverse(item)}>{item}</button>
            ))}
          </div>
          <div className="form-grid">
            <label className="field"><span>Minimum Gap</span><select value={filters.minGap} onChange={(event) => setFilters((current) => ({ ...current, minGap: event.target.value }))}><option>{'>= 0.5%'}</option><option>{'>= 1%'}</option><option>{'>= 2%'}</option></select></label>
            <label className="field"><span>Volume Filter</span><select value={filters.minVolume} onChange={(event) => setFilters((current) => ({ ...current, minVolume: event.target.value }))}><option>{'>= 1.5x avg'}</option><option>{'>= 2x avg'}</option><option>{'>= 3x avg'}</option></select></label>
            <label className="field"><span>News Filter</span><select value={filters.news} onChange={(event) => setFilters((current) => ({ ...current, news: event.target.value }))}><option>Required</option><option>Preferred</option><option>Ignore</option></select></label>
            <label className="field"><span>Minimum ML</span><select value={filters.minMl} onChange={(event) => setFilters((current) => ({ ...current, minMl: event.target.value }))}><option>{'>= 50'}</option><option>{'>= 55'}</option><option>{'>= 65'}</option></select></label>
            <label className="field"><span>Max Risk</span><select value={filters.maxRisk} onChange={(event) => setFilters((current) => ({ ...current, maxRisk: event.target.value }))}><option>{'<= 45'}</option><option>{'<= 55'}</option><option>{'<= 65'}</option></select></label>
            <label className="field"><span>Stop / Target Plan</span><select value={`${filters.stopMethod} | ${filters.targetPlan}`} onChange={(event) => {
              const [stopMethod, targetPlan] = event.target.value.split(' | ');
              setFilters((current) => ({ ...current, stopMethod, targetPlan }));
            }}><option>Opening range / swing low-high | T1 1R / T2 2R</option><option>VWAP invalidation | T1 VWAP extension / T2 2R</option><option>ATR 1.2x | T1 0.8R / T2 1.5R</option></select></label>
          </div>
          <div className="module-grid">
            {analysisModules.map((module) => (
              <label key={module} className="check-tile">
                <input type="checkbox" defaultChecked />
                <span>{module}</span>
              </label>
            ))}
          </div>
        </TerminalPanel>

        <TerminalPanel eyebrow="Validation Engine" title="Expected vs Actual Performance">
          <div className="metric-grid metric-grid--compact">
            <MetricTile label="Prediction Accuracy" value="Not validated" icon={Target} tone="warn" />
            <MetricTile label="ML Accuracy" value="Not validated" icon={BarChart3} tone="warn" />
            <MetricTile label="Entry Valid" value="Not validated" icon={CheckCircle2} tone="warn" />
            <MetricTile label="Confidence Change" value="Not validated" icon={TrendingUp} tone="warn" />
          </div>
          <DataTable
            columns={['Metric', 'Premarket', '9:08 AM', 'Open', 'Current']}
            rows={[
              ['Expected Price', 'Validation not run', '-', '-', '-'],
              ['Trend Confirmation', 'Validation not run', '-', '-', '-'],
              ['Volume Confirmation', 'Validation not run', '-', '-', '-'],
              ['Stop Loss Validation', 'Validation not run', '-', '-', '-'],
            ]}
          />
        </TerminalPanel>
      </div>

      <TerminalPanel
        eyebrow="9:08 Open Confirmation"
        title="Validated Opening Candidates"
        description={`Data freshness: ${openPayload?.created_at || 'Not available'}`}
        actions={<><label className="toggle-pill"><input type="checkbox" checked={openAutoRefresh} onChange={(event) => setOpenAutoRefresh(event.target.checked)} /> Auto-refresh</label><button className="btn-secondary" onClick={() => loadOpenConfirmation()}><RefreshCw size={15} /> Retry</button><button className="btn-secondary" onClick={exportOpenConfirmationCsv} disabled={!openRows.length}><Download size={15} /> Export</button></>}
      >
        <Toolbar search={openQuery} setSearch={setOpenQuery} />
        {openError && <div className="status-badge status-bad">{openError}</div>}
        <DataTable
          columns={['Symbol', 'Open Price', 'Price 9:08', 'Gap Hold', 'VWAP', 'Volume', 'Confirmation', 'Decision', 'Reason']}
          rows={openRows.map((row: any) => {
            const validation = row.market_open_validation || {};
            const analysis = row.market_open_analysis || {};
            return [
              <strong key="s">{row.symbol || row.stock}</strong>,
              analysis.market_open_price || row.open || '-',
              analysis.target_time_price || row.live_price || '-',
              validation.gap_hold_percent || '-',
              validation.vwap_status || '-',
              row.volume_strength || '-',
              validation.market_open_confirmation_score || row.ml_probability || '-',
              row.action || row.premarket_action || row.signal || '-',
              row.reason || row.trade_reason || row.quality_filter_reasons || '-',
            ];
          })}
          emptyTitle={openLoading ? 'Loading open confirmation' : 'No confirmed stocks yet'}
          emptyBody={openLoading ? 'Reading backend 9:08 confirmation results.' : 'Run Premarket first, then run 9:08 confirmation from this same pipeline page.'}
        />
      </TerminalPanel>

      <TerminalPanel eyebrow="Qualified Stocks" title="Premarket Recommendations">
        <Toolbar
          search={query}
          setSearch={setQuery}
          right={<select value={displayLimit} onChange={(event) => setDisplayLimit(Number(event.target.value))}><option value={10}>Top 10</option><option value={25}>Top 25</option></select>}
        />
        <StockGrid items={visibleStocks} loading={loading && !visibleStocks.length} />
      </TerminalPanel>

      <TerminalPanel eyebrow="Visual Analytics" title="Comparison Dashboard">
        <div className="analytics-strip">
          <ProgressLine label="Trend Confirmation: validation not run" value={0} />
          <ProgressLine label="Volume Confirmation: validation not run" value={0} />
          <ProgressLine label="Entry Validation: validation not run" value={0} />
          <ProgressLine label="Stop Loss Validation: validation not run" value={0} />
        </div>
      </TerminalPanel>
    </main>
  );
}
