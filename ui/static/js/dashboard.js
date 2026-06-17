/* External Dashboard JS adapted from inline script in dashboard.html.
	 It keeps the original UI wiring and replaces SVG history/candlestick with Chart.js charts. */

let form;
let savedList;
let tableRegion;
let detailRegion;
let breadthRegion;
let sectorRegion;
let compareRegion;
let historyRegion;
let sessionStatus;
let progressState;
let reportPath;
let autoStatus;
let exportIntraday;
let exportSwing;
let loadDemo;
let scanWatchlist;
let scanAll;
let scanNow;
let heroScanWatchlist;
let heroScanAll;
let heroScanNow;
let compareReportsBtn;
let exportCurrentCsvBtn;
let intradayExportCsvBtn;
let swingExportCsvBtn;
let autoRefreshInput;
let refreshMinutesInput;
let premarketRunBtn;
let premarketCustomRunBtn;
let intradayCustomRunBtn;
let swingCustomRunBtn;
let saveSettingsBtn;
let watchlistEditor;
let watchlistPreview;
let watchlistCount;
let saveWatchlistBtn;
let applyWatchlistBtn;
let resetWatchlistBtn;
let saveStrategyBtn;
let loadStrategyBtn;
let deleteStrategyBtn;
let refreshStrategiesBtn;
let advancedScanPanel;
let advancedSettingsToggle;
let toggleIntradayCustomBtn;
let toggleSwingCustomBtn;
let intradayCustomPanel;
let swingCustomPanel;
let scanStatusCard;
let scanProgressFill;
let scanProgressLabel;
let scanProgressPercent;
let scanStageList;
let reportSearchInput;
let reportModeFilter;
let reportsCount;
let pinnedScan;
let pinnedScanTitle;
let pinnedScanSubtitle;
let marketTime;
let marketStatus;
let intradayCurrentStatus;
let intradayProgressFill;
let intradayRecentType;
let swingCurrentStatus;
let swingProgressFill;
let swingRecentType;

const DEFAULT_WATCHLIST = ['RELIANCE.NS', 'INFY.NS', 'TCS.NS', 'HDFCBANK.NS', 'ICICIBANK.NS', 'SBIN.NS', 'LT.NS', 'ADANIENT.NS'];
const WATCHLIST_STORAGE_KEY = 'scanner_watchlist_symbols';
const ACTIVE_SCAN_STORAGE_KEY = 'scanner_active_scan';
const SETTINGS_STORAGE_KEY = 'scanner_settings';

const summaryEls = {
	qualified: document.getElementById('qualified-count'),
	avgGrade: document.getElementById('avg-grade'),
	avgMl: document.getElementById('avg-ml'),
	split: document.getElementById('horizon-split'),
	avgEvent: document.getElementById('avg-event'),
};

let latestPayload = null;
let latestRanked = [];
let activeStock = null;
let autoRefreshTimer = null;
let scanMode = 'watchlist';
let lastDataFreshness = null;

let historyChart = null;
let candleChart = null;

// Utility: debounce
function debounce(fn, wait=250){ let t; return (...args)=>{ clearTimeout(t); t=setTimeout(()=>fn(...args), wait); }; }

function normalizeSymbols(input) {
	const raw = Array.isArray(input) ? input.join(' ') : String(input || '');
	const seen = new Set();
	return raw
		.replace(/,/g, ' ')
		.split(/\s+/)
		.map(symbol => symbol.trim().toUpperCase())
		.filter(Boolean)
		.filter(symbol => {
			if (seen.has(symbol)) return false;
			seen.add(symbol);
			return true;
		});
}

function getStoredWatchlist() {
	try {
		const stored = JSON.parse(localStorage.getItem(WATCHLIST_STORAGE_KEY) || '[]');
		const normalized = normalizeSymbols(stored);
		return normalized.length ? normalized : DEFAULT_WATCHLIST.slice();
	} catch (error) {
		return DEFAULT_WATCHLIST.slice();
	}
}

function setSymbolsTextarea(symbols) {
	const field = document.getElementById('symbols');
	if (field) field.value = normalizeSymbols(symbols).join(' ');
}

function toggleAdvancedSettings() {
	if (!advancedScanPanel || !advancedSettingsToggle) return;
	const isExpanded = advancedScanPanel.classList.toggle('expanded');
	advancedScanPanel.classList.toggle('collapsed', !isExpanded);
	advancedSettingsToggle.textContent = isExpanded ? 'Hide advanced settings' : 'Show advanced settings';
}

function togglePanel(panel, button, showLabel, hideLabel) {
	if (!panel || !button) return;
	const isHidden = panel.classList.toggle('hidden-panel');
	button.textContent = isHidden ? showLabel : hideLabel;
}

function toggleIntradayCustomScan() {
	togglePanel(intradayCustomPanel, toggleIntradayCustomBtn, 'Show custom intraday scan', 'Hide custom intraday scan');
}

function toggleSwingCustomScan() {
	togglePanel(swingCustomPanel, toggleSwingCustomBtn, 'Show custom swing scan', 'Hide custom swing scan');
}

function renderWatchlistEditor() {
	if (!watchlistEditor) return;
	const symbols = normalizeSymbols(watchlistEditor.value);
	if (watchlistCount) watchlistCount.textContent = `${symbols.length} symbol${symbols.length === 1 ? '' : 's'}`;
	if (!watchlistPreview) return;
	watchlistPreview.innerHTML = symbols.length
		? symbols.map(symbol => `<span class="watch-chip">${symbol}</span>`).join('')
		: '<span class="muted">No symbols yet</span>';
}

function loadWatchlistEditor(settings = {}) {
	if (!watchlistEditor) return;
	const fromSettings = normalizeSymbols(settings.watchlist || []);
	const hasLocalWatchlist = !!localStorage.getItem(WATCHLIST_STORAGE_KEY);
	const symbols = hasLocalWatchlist ? getStoredWatchlist() : (fromSettings.length ? fromSettings : DEFAULT_WATCHLIST);
	watchlistEditor.value = symbols.join(' ');
	renderWatchlistEditor();
	if (!normalizeSymbols(document.getElementById('symbols')?.value).length) setSymbolsTextarea(symbols);
}

function getWatchlistSymbols() {
	const symbols = normalizeSymbols(watchlistEditor?.value || localStorage.getItem(WATCHLIST_STORAGE_KEY) || DEFAULT_WATCHLIST.join(' '));
	return symbols.length ? symbols : DEFAULT_WATCHLIST.slice();
}

function saveWatchlist(showToast = true) {
	const symbols = getWatchlistSymbols();
	localStorage.setItem(WATCHLIST_STORAGE_KEY, JSON.stringify(symbols));
	if (watchlistEditor) watchlistEditor.value = symbols.join(' ');
	renderWatchlistEditor();
	if (scanMode === 'watchlist') setSymbolsTextarea(symbols);
	if (showToast) setScanState('idle', `Watchlist saved (${symbols.length} symbols)`, 0);
	return symbols;
}

function applyWatchlistToForm() {
	const symbols = saveWatchlist(false);
	scanMode = 'watchlist';
	const autoUniverse = document.getElementById('auto_nse_universe');
	if (autoUniverse) autoUniverse.checked = false;
	setSymbolsTextarea(symbols);
	updateModeButtons();
	setScanState('idle', 'Watchlist loaded into scan form', 0);
}

function resetWatchlist() {
	if (watchlistEditor) watchlistEditor.value = DEFAULT_WATCHLIST.join(' ');
	saveWatchlist(false);
	applyWatchlistToForm();
}

function modeLabel(mode = scanMode) {
	const labels = {
		watchlist: 'Watchlist',
		all: 'Full NSE',
		premarket: 'Premarket',
		'premarket-custom': 'Premarket Custom',
		'intraday-custom': 'Custom Intraday',
		'swing-custom': 'Custom Swing',
		standard: 'Standard',
	};
	return labels[mode] || String(mode || 'Standard');
}

function isPremarketWindow() {
	const parts = new Intl.DateTimeFormat('en-GB', {
		timeZone: 'Asia/Kolkata',
		hour: '2-digit',
		minute: '2-digit',
		hour12: false,
	}).formatToParts(new Date());
	const hour = Number(parts.find(part => part.type === 'hour')?.value || 0);
	const minute = Number(parts.find(part => part.type === 'minute')?.value || 0);
	const total = hour * 60 + minute;
	return total >= 7 * 60 && total <= 9 * 60 + 15;
}

function saveActiveScan(scanId, payload) {
	localStorage.setItem(ACTIVE_SCAN_STORAGE_KEY, JSON.stringify({
		scan_id: scanId,
		started_at: Date.now(),
		scan_mode: payload?.scan_mode || scanMode,
		payload: payload || {},
	}));
}

function readActiveScan() {
	try {
		const record = JSON.parse(localStorage.getItem(ACTIVE_SCAN_STORAGE_KEY) || '{}');
		return record.scan_id ? record : null;
	} catch (error) {
		return null;
	}
}

function clearActiveScan() {
	localStorage.removeItem(ACTIVE_SCAN_STORAGE_KEY);
}

function setScanState(state, label, percent) {
	const pct = Math.max(0, Math.min(100, Number(percent) || 0));
	if (scanStatusCard) scanStatusCard.dataset.state = state || 'idle';
	if (scanProgressFill) scanProgressFill.style.width = `${pct}%`;
	if (scanProgressLabel) scanProgressLabel.textContent = label || 'Ready';
	if (scanProgressPercent) scanProgressPercent.textContent = `${Math.round(pct)}%`;
	if (progressState) progressState.textContent = label || 'Waiting';

	const stages = scanStageList ? [...scanStageList.querySelectorAll('.stage')] : [];
	stages.forEach((stage, index) => {
		const threshold = [5, 25, 55, 80, 100][index] || 100;
		stage.classList.toggle('completed', pct >= threshold);
		stage.classList.toggle('active', pct < threshold && pct >= (index === 0 ? 0 : [5, 25, 55, 80][index - 1]));
	});
	updatePinnedScan(state || 'idle', label || 'Ready', state === 'running' ? 'Scanning for Stocks' : `Recent scan: ${modeLabel(scanMode)}`);
}

function runningPercent(startedAt) {
	const elapsed = Math.max(0, Date.now() - Number(startedAt || Date.now()));
	return Math.min(92, 12 + Math.floor(elapsed / 1500));
}

// Global filter helper (uses DOM controls if present)
function getFilteredRecords(records){ if(!records) return [];
	let out = records.slice();
	const tableSearch = document.getElementById('table-search');
	const tableHorizonFilter = document.getElementById('table-horizon-filter');
	const tableSort = document.getElementById('table-sort');
	const pageSize = document.getElementById('page-size');
	const q = tableSearch?.value?.toLowerCase?.() || '';
	const horizon = tableHorizonFilter?.value || 'all';
	if(q){ out = out.filter(r=> (r.stock||'').toLowerCase().includes(q) || (r.sector||'').toLowerCase().includes(q) ); }
	if(horizon && horizon !== 'all'){ out = out.filter(r=> (r.best_horizon||'').toLowerCase() === horizon); }
	const sort = tableSort?.value || 'rank';
	if(sort === 'grade'){ out.sort((a,b)=> (Number(b.premarket_grade)||0) - (Number(a.premarket_grade)||0)); }
	else if(sort === 'ml'){ out.sort((a,b)=> (Number(b.ml_probability)||0) - (Number(a.ml_probability)||0)); }
	else { out.sort((a,b)=> (Number(a.rank)||0) - (Number(b.rank)||0)); }
	const size = Number(pageSize?.value || 25);
	return out.slice(0, size);
}

function safe(value, fallback = '–') { return value === null || value === undefined || value === '' ? fallback : value; }
function num(value, digits = 2) { const parsed = Number(value); return Number.isFinite(parsed) ? parsed.toFixed(digits) : '–'; }
function badgeClass(text) { const normalized = String(text || '').toUpperCase(); if (normalized.includes('BUY')) return 'buy'; if (normalized.includes('SELL')) return 'sell'; return 'watch'; }
function isChartReady() { return typeof window.Chart !== 'undefined'; }

function priceValue(row) { return row?.live_price ?? row?.current_price ?? row?.last_close ?? row?.expected_open; }

function currentProgressPercent() {
	const parsed = Number(String(scanProgressPercent?.textContent || '0').replace(/[^\d.]/g, ''));
	return Number.isFinite(parsed) ? parsed : 0;
}

function updatePinnedScan(state = 'idle', title = 'No active scan', subtitle = '') {
	const pct = currentProgressPercent();
	if (pinnedScan) pinnedScan.dataset.state = state;
	if (pinnedScanTitle) pinnedScanTitle.textContent = title;
	if (pinnedScanSubtitle) pinnedScanSubtitle.textContent = subtitle || `Recent scan: ${modeLabel(scanMode)}`;
	if (intradayCurrentStatus) intradayCurrentStatus.textContent = title;
	if (swingCurrentStatus) swingCurrentStatus.textContent = title;
	if (intradayProgressFill) intradayProgressFill.style.width = `${pct}%`;
	if (swingProgressFill) swingProgressFill.style.width = `${pct}%`;
	if (intradayRecentType) intradayRecentType.textContent = `Recent: ${modeLabel(scanMode)}`;
	if (swingRecentType) swingRecentType.textContent = `Recent: ${modeLabel(scanMode)}`;
}

function getMarketClock() {
	const parts = new Intl.DateTimeFormat('en-GB', {
		timeZone: 'Asia/Kolkata',
		weekday: 'short',
		hour: '2-digit',
		minute: '2-digit',
		second: '2-digit',
		hour12: false,
	}).formatToParts(new Date());
	const get = type => parts.find(part => part.type === type)?.value || '';
	const hour = Number(get('hour') || 0);
	const minute = Number(get('minute') || 0);
	const total = hour * 60 + minute;
	const isWeekday = !['Sat', 'Sun'].includes(get('weekday'));
	const preOpen = isWeekday && total >= 9 * 60 && total < 9 * 60 + 15;
	const open = isWeekday && total >= 9 * 60 + 15 && total <= 15 * 60 + 30;
	return {
		time: `${get('hour')}:${get('minute')}:${get('second')} IST`,
		status: open ? 'Market Open' : preOpen ? 'Pre-open' : 'Market Closed',
		state: open ? 'open' : preOpen ? 'preopen' : 'closed',
	};
}

function renderMarketClock() {
	const clock = getMarketClock();
	if (marketTime) marketTime.textContent = clock.time;
	if (marketStatus) marketStatus.textContent = clock.status;
	document.getElementById('market-clock')?.setAttribute('data-state', clock.state);
}

function downloadCsv(rows, filename) {
	if (!rows || !rows.length) {
		alert('No rows available to export.');
		return;
	}
	const headers = Object.keys(rows[0]);
	const csv = [
		headers.join(','),
		...rows.map(row => headers.map(key => JSON.stringify(row[key] ?? '')).join(',')),
	].join('\n');
	const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
	const url = URL.createObjectURL(blob);
	const link = document.createElement('a');
	link.href = url;
	link.download = filename;
	document.body.appendChild(link);
	link.click();
	document.body.removeChild(link);
	URL.revokeObjectURL(url);
}

function getCurrentCsvRows() {
	return getFilteredRecords(latestPayload?.ranked || latestRanked || []).map(row => ({
		stock: row.stock,
		current_price: priceValue(row),
		action: row.premarket_action || row.trade_type,
		horizon: row.best_horizon,
		grade: row.premarket_grade,
		ml_probability: row.ml_probability,
		score: row.score,
		confidence_pct: row.confidence_pct,
		event_score: row.event_score,
		risk_reward: row.risk_reward,
	}));
}

function updateModeButtons() {
	if (scanWatchlist) {
		scanWatchlist.classList.toggle('primary', scanMode === 'watchlist');
		scanWatchlist.classList.toggle('secondary', scanMode !== 'watchlist');
	}
	if (scanAll) {
		scanAll.classList.toggle('primary', scanMode === 'all');
		scanAll.classList.toggle('secondary', scanMode !== 'all');
	}
}

const runWatchlistScan = () => {
	scanMode = 'watchlist';
	const autoUniverse = document.getElementById('auto_nse_universe');
	if (autoUniverse) autoUniverse.checked = false;
	setSymbolsTextarea(saveWatchlist(false));
	updateModeButtons();
	showPage('scan');
	startScan();
};

const runFullScan = () => {
	scanMode = 'all';
	const autoUniverse = document.getElementById('auto_nse_universe');
	if (autoUniverse) autoUniverse.checked = true;
	setSymbolsTextarea([]);
	updateModeButtons();
	showPage('scan');
	startScan();
};

const runNow = () => {
	if (!normalizeSymbols(document.getElementById('symbols')?.value).length && !document.getElementById('auto_nse_universe')?.checked) {
		setSymbolsTextarea(getWatchlistSymbols());
		scanMode = 'watchlist';
	}
	showPage('scan');
	startScan();
};

function setScanFormFromPremarket() {
  document.getElementById('auto_nse_universe').checked = document.getElementById('premarket_auto_nse_universe').checked;
  document.getElementById('symbols').value = document.getElementById('premarket_symbols').value || '';
  document.getElementById('period').value = document.getElementById('premarket_period').value;
  document.getElementById('interval').value = document.getElementById('premarket_interval').value;
  document.getElementById('top_n').value = document.getElementById('premarket_top_n').value;
  document.getElementById('workers').value = document.getElementById('premarket_workers').value;
  document.getElementById('strict_shortlist').checked = document.getElementById('premarket_strict_shortlist').checked;
}

function setScanFormFromCustom(type) {
  const symbols = document.getElementById(`${type}-custom-symbols`)?.value || '';
  if (!symbols.trim()) return false;
  document.getElementById('symbols').value = symbols;
  document.getElementById('period').value = '6mo';
  document.getElementById('interval').value = '1d';
  document.getElementById('auto_nse_universe').checked = false;
  document.getElementById('strict_shortlist').checked = true;
  document.getElementById('top_n').value = 20;
  document.getElementById('workers').value = 5;
  return true;
}

function runPremarketScan() {
  scanMode = 'premarket';
  setScanFormFromPremarket();
  updateModeButtons();
  showPage('premarket');
  if (!isPremarketWindow()) setScanState('idle', 'Premarket template selected outside pre-open window', 0);
  startScan();
}

function runPremarketCustomScan() {
  scanMode = 'premarket-custom';
  setScanFormFromPremarket();
  document.getElementById('auto_nse_universe').checked = false;
  updateModeButtons();
  showPage('premarket');
  startScan();
}

function runIntradayCustomScan() {
  if (!setScanFormFromCustom('intraday')) {
    alert('Enter at least one custom symbol for intraday scan.');
    return;
  }
  scanMode = 'intraday-custom';
  updateModeButtons();
  showPage('intraday');
  startScan();
}

function runSwingCustomScan() {
  if (!setScanFormFromCustom('swing')) {
    alert('Enter at least one custom symbol for swing scan.');
    return;
  }
  scanMode = 'swing-custom';
  updateModeButtons();
  showPage('swing');
  startScan();
}

function saveSettings() {
  const settings = {
    default_scan_type: document.getElementById('default_scan_type').value,
    default_premarket_universe: document.getElementById('default_premarket_universe').value,
    default_intraday_horizon: document.getElementById('default_intraday_horizon').value,
    default_swing_risk: document.getElementById('default_swing_risk').value,
    enable_notifications: document.getElementById('enable_notifications').checked,
    settings_notify_telegram: document.getElementById('settings_notify_telegram')?.checked || false,
    settings_telegram_category: document.getElementById('settings_telegram_category')?.value || 'Premarket',
    auto_refresh: document.getElementById('settings_auto_refresh')?.checked || false,
    custom_scan_filters: document.getElementById('custom_scan_filters').value,
    watchlist: getWatchlistSymbols(),
    ui_theme: document.getElementById('ui_theme')?.value || 'dark',
    default_period: document.getElementById('settings_default_period')?.value || '6mo',
    default_interval: document.getElementById('settings_default_interval')?.value || '1d',
    top_n: Number(document.getElementById('settings_top_n')?.value || 25),
    workers: Number(document.getElementById('settings_workers')?.value || 8),
    min_grade: Number(document.getElementById('settings_min_grade')?.value || 0),
    min_ml_probability: Number(document.getElementById('settings_min_ml')?.value || 45),
    min_confidence: Number(document.getElementById('settings_min_confidence')?.value || 50),
    min_risk_reward: Number(document.getElementById('settings_min_rr')?.value || 1.5),
    min_volume: Number(document.getElementById('settings_min_volume')?.value || 100000),
    max_volatility: Number(document.getElementById('settings_max_volatility')?.value || 8),
    position_size_pct: Number(document.getElementById('settings_position_size')?.value || 10),
    stop_buffer_pct: Number(document.getElementById('settings_stop_buffer')?.value || 0.5),
    sector_limit: Number(document.getElementById('settings_sector_limit')?.value || 5),
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  })
    .then(response => response.json())
    .then(result => {
      if (result.status === 'ok') {
        setScanState('idle', 'Settings saved', 0);
      } else {
        console.warn('Server settings save failed', result);
        setScanState('error', 'Settings saved locally only', 0);
      }
    })
    .catch(error => {
      console.warn('Failed to save settings to server', error);
      setScanState('error', 'Settings saved locally only', 0);
    });
}

async function loadSettings() {
  let settings = {};
  try {
    const response = await fetch('/api/settings');
    if (response.ok) {
      const payload = await response.json();
      settings = payload.settings || {};
    }
  } catch (error) {
    console.warn('Failed to load server settings', error);
  }

  const stored = localStorage.getItem(SETTINGS_STORAGE_KEY);
  if (stored) {
    try { settings = { ...settings, ...JSON.parse(stored) }; } catch (e) { console.warn('Invalid local settings', e); }
  }

  document.getElementById('default_scan_type').value = settings.default_scan_type || 'premarket';
  document.getElementById('default_premarket_universe').value = settings.default_premarket_universe || 'both';
  document.getElementById('default_intraday_horizon').value = settings.default_intraday_horizon || '3h';
  document.getElementById('default_swing_risk').value = settings.default_swing_risk || 'balanced';
  document.getElementById('enable_notifications').checked = !!settings.enable_notifications;
  document.getElementById('settings_notify_telegram')?.checked = !!settings.settings_notify_telegram;
  if (document.getElementById('settings_telegram_category')) document.getElementById('settings_telegram_category').value = settings.settings_telegram_category || 'Premarket';
  const settingsAutoRefresh = document.getElementById('settings_auto_refresh');
  if (settingsAutoRefresh) settingsAutoRefresh.checked = !!settings.auto_refresh;
  document.getElementById('custom_scan_filters').value = settings.custom_scan_filters || '';
  if (document.getElementById('settings_default_period')) document.getElementById('settings_default_period').value = settings.default_period || '6mo';
  if (document.getElementById('settings_default_interval')) document.getElementById('settings_default_interval').value = settings.default_interval || '1d';
  if (document.getElementById('settings_top_n')) document.getElementById('settings_top_n').value = settings.top_n || 25;
  if (document.getElementById('settings_workers')) document.getElementById('settings_workers').value = settings.workers || 8;
  if (document.getElementById('settings_min_grade')) document.getElementById('settings_min_grade').value = settings.min_grade ?? 0;
  if (document.getElementById('settings_min_ml')) document.getElementById('settings_min_ml').value = settings.min_ml_probability ?? 45;
  if (document.getElementById('settings_min_confidence')) document.getElementById('settings_min_confidence').value = settings.min_confidence ?? 50;
  if (document.getElementById('settings_min_rr')) document.getElementById('settings_min_rr').value = settings.min_risk_reward ?? 1.5;
  if (document.getElementById('settings_min_volume')) document.getElementById('settings_min_volume').value = settings.min_volume ?? 100000;
  if (document.getElementById('settings_max_volatility')) document.getElementById('settings_max_volatility').value = settings.max_volatility ?? 8;
  if (document.getElementById('settings_position_size')) document.getElementById('settings_position_size').value = settings.position_size_pct ?? 10;
  if (document.getElementById('settings_stop_buffer')) document.getElementById('settings_stop_buffer').value = settings.stop_buffer_pct ?? 0.5;
  if (document.getElementById('settings_sector_limit')) document.getElementById('settings_sector_limit').value = settings.sector_limit ?? 5;
	if (settings.watchlist?.length && !localStorage.getItem(WATCHLIST_STORAGE_KEY)) {
		localStorage.setItem(WATCHLIST_STORAGE_KEY, JSON.stringify(normalizeSymbols(settings.watchlist)));
	}
	loadWatchlistEditor(settings);
	if (settings.ui_theme === 'light') {
		document.body.classList.remove('theme-dark');
	} else {
		document.body.classList.add('theme-dark');
	}
}

function getStrategyPayload() {
	return {
		strategy_id: document.getElementById('settings_strategy_selector')?.value || '',
		name: document.getElementById('strategy_name')?.value.trim() || '',
		description: document.getElementById('strategy_description')?.value.trim() || '',
		horizon: document.getElementById('strategy_horizon')?.value || 'premarket',
		symbols: normalizeSymbols(document.getElementById('strategy_symbols')?.value || ''),
		filters: document.getElementById('strategy_filters')?.value.trim() || '',
	};
}

function renderStrategyOptions(strategies) {
	const selector = document.getElementById('settings_strategy_selector');
	if (!selector) return;
	selector.innerHTML = '<option value="">Select strategy</option>' + (strategies || []).map(strategy => `
			<option value="${strategy.strategy_id}">${strategy.name} (${strategy.horizon || 'unknown'})</option>
		`).join('');
}

async function fetchStrategies() {
	try {
		const response = await fetch('/api/strategies');
		if (!response.ok) throw new Error('Failed to fetch strategies');
		const payload = await response.json();
		const strategies = payload.strategies || [];
		renderStrategyOptions(strategies);
		renderStrategyLibrary(strategies);
	} catch (error) {
		console.warn('Failed to fetch strategies', error);
		renderStrategyLibrary([]);
	}
}

function renderStrategyLibrary(strategies) {
	const container = document.getElementById('strategy-library');
	if (!container) return;
	if (!strategies || !strategies.length) {
		container.innerHTML = '<div class="empty-state">No strategies saved yet.</div>';
		return;
	}
	container.innerHTML = strategies.map(strategy => `
		<div class="saved-item strategy-item" data-strategy-id="${strategy.strategy_id}">
			<div class="strategy-summary"><strong>${safe(strategy.name)}</strong> · ${safe(strategy.horizon)}<span class="mode-pill">${safe(strategy.horizon)}</span></div>
			<div class="strategy-meta"><span>${safe(strategy.description)}</span></div>
			<div class="actions"><button class="button secondary" data-action="load-strategy" data-strategy-id="${strategy.strategy_id}" type="button">Load</button><button class="button danger-action" data-action="delete-strategy" data-strategy-id="${strategy.strategy_id}" type="button">Delete</button></div>
		</div>
	`).join('');
	container.querySelectorAll('[data-action="load-strategy"]').forEach(btn => btn.addEventListener('click', async () => {
		const strategyId = btn.dataset.strategyId;
		if (!strategyId) return;
		const response = await fetch(`/api/strategies/${strategyId}`);
		if (!response.ok) { alert('Failed to load strategy'); return; }
		const payload = await response.json();
		if (payload.strategy) {
			populateStrategyForm(payload.strategy);
			applyStrategyToForm(payload.strategy);
			showPage('scan');
			setScanState('idle', `Loaded strategy ${payload.strategy.name}`, 0);
		}
	}));
	container.querySelectorAll('[data-action="delete-strategy"]').forEach(btn => btn.addEventListener('click', async () => {
		const strategyId = btn.dataset.strategyId;
		if (!strategyId || !confirm('Delete selected strategy?')) return;
		const response = await fetch(`/api/strategies/${strategyId}`, { method: 'DELETE' });
		const result = await response.json();
		if (result.status === 'ok') {
			await fetchStrategies();
			setScanState('idle', 'Strategy deleted', 0);
		} else {
			alert('Delete failed: ' + (result.message || 'unknown error'));
		}
	}));
}

function populateStrategyForm(strategy) {
	if (!strategy) return;
	document.getElementById('strategy_name').value = strategy.name || '';
	document.getElementById('strategy_description').value = strategy.description || '';
	if (document.getElementById('strategy_horizon')) document.getElementById('strategy_horizon').value = strategy.horizon || 'premarket';
	document.getElementById('strategy_symbols').value = normalizeSymbols(Array.isArray(strategy.symbols) ? strategy.symbols.join(' ') : strategy.symbols || '').join(' ');
	document.getElementById('strategy_filters').value = strategy.filters || '';
}

function applyStrategyToForm(strategy) {
	if (!strategy) return;
	const symbols = normalizeSymbols(Array.isArray(strategy.symbols) ? strategy.symbols.join(' ') : strategy.symbols || '');
	if (symbols.length) {
		setSymbolsTextarea(symbols.join(' '));
	}
	if (strategy.filters && document.getElementById('custom_scan_filters')) {
		document.getElementById('custom_scan_filters').value = strategy.filters;
	}
	const mapping = { premarket: 'watchlist', intraday: 'intraday-custom', swing: 'swing-custom' };
	if (strategy.horizon && mapping[strategy.horizon]) {
		scanMode = mapping[strategy.horizon];
		updateModeButtons();
	}
}

async function saveStrategy() {
	const payload = getStrategyPayload();
	if (!payload.name) {
		alert('Enter a name for the strategy before saving.');
		return;
	}
	try {
		const response = await fetch('/api/strategies', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(payload),
		});
		const result = await response.json();
		if (result.status === 'ok') {
			setScanState('idle', 'Strategy saved', 0);
			await fetchStrategies();
			if (document.getElementById('settings_strategy_selector')) document.getElementById('settings_strategy_selector').value = result.strategy.strategy_id;
		} else {
			alert('Strategy save failed: ' + (result.message || 'unknown error'));
		}
	} catch (error) {
		console.warn('Save strategy failed', error);
		alert('Save strategy failed. See console for details.');
	}
}

async function loadStrategy() {
	const selector = document.getElementById('settings_strategy_selector');
	if (!selector || !selector.value) {
		alert('Select a strategy first.');
		return;
	}
	try {
		const response = await fetch(`/api/strategies/${selector.value}`);
		if (!response.ok) throw new Error('Strategy not found');
		const payload = await response.json();
		if (payload.strategy) {
			populateStrategyForm(payload.strategy);
			applyStrategyToForm(payload.strategy);
			setScanState('idle', 'Strategy loaded', 0);
		}
	} catch (error) {
		console.warn('Load strategy failed', error);
		alert('Load strategy failed.');
	}
}

async function deleteStrategy() {
	const selector = document.getElementById('settings_strategy_selector');
	if (!selector || !selector.value) {
		alert('Select a strategy first.');
		return;
	}
	if (!confirm('Delete selected strategy?')) {
		return;
	}
	try {
		const response = await fetch(`/api/strategies/${selector.value}`, {
			method: 'DELETE',
		});
		const result = await response.json();
		if (result.status === 'ok') {
			setScanState('idle', 'Strategy deleted', 0);
			await fetchStrategies();
			if (document.getElementById('settings_strategy_selector')) document.getElementById('settings_strategy_selector').value = '';
		} else {
			alert('Delete failed: ' + (result.message || 'unknown error'));
		}
	} catch (error) {
		console.warn('Delete strategy failed', error);
		alert('Delete strategy failed.');
	}
}

function getPayloadFromForm() {
	const autoUniverse = document.getElementById('auto_nse_universe').checked;
	let symbols = document.getElementById('symbols').value;
	if (!autoUniverse && !normalizeSymbols(symbols).length) {
		symbols = getWatchlistSymbols().join(' ');
		setSymbolsTextarea(symbols);
	}
	return {
		symbols,
		period: document.getElementById('period').value,
		interval: document.getElementById('interval').value,
		top_n: Number(document.getElementById('top_n').value || 10),
		workers: Number(document.getElementById('workers').value || 5),
		candidate_pool: Number(document.getElementById('candidate_pool').value || 150),
		validation_pool: Number(document.getElementById('validation_pool').value || 25),
		benchmark: document.getElementById('benchmark').value || '^NSEI',
		strict_shortlist: document.getElementById('strict_shortlist').checked,
		auto_nse_universe: autoUniverse,
		scan_mode: scanMode,
		market_open_analysis: document.getElementById('market_open_analysis')?.checked || false,
		market_open_time: document.getElementById('market_open_time')?.value || '09:08',
		market_open_interval: document.getElementById('market_open_interval')?.value || '1m',
		notify_telegram: document.getElementById('notify_telegram')?.checked || false,
		telegram_category: document.getElementById('telegram_category')?.value || 'Premarket',
		strategy_id: document.getElementById('settings_strategy_selector')?.value || '',
		strategy_name: document.getElementById('strategy_name')?.value.trim(),
		strategy_description: document.getElementById('strategy_description')?.value.trim(),
		strategy_horizon: document.getElementById('strategy_horizon')?.value || '',
		strategy_symbols: normalizeSymbols(document.getElementById('strategy_symbols')?.value || '').join(' '),
		strategy_filters: document.getElementById('strategy_filters')?.value || '',
		custom_scan_filters: document.getElementById('custom_scan_filters')?.value || '',
		watchlist: getWatchlistSymbols(),
		analysis_settings: JSON.parse(localStorage.getItem(SETTINGS_STORAGE_KEY) || '{}'),
	};
}

async function fetchSavedScans() {
	try { const response = await fetch('/api/scans'); const payload = await response.json(); renderSavedScans(payload.scans || []); } catch (error) { console.warn('Saved scans unavailable', error); }
}

function renderSavedScans(scans) {
	if (!savedList) return;
	if (!scans || !scans.length) { savedList.innerHTML = '<div class="empty-state">No saved scans yet.</div>'; return; }
	savedList.innerHTML = scans.map(scan => `
			<div class="saved-item" data-scan-id="${scan.scan_id}">
				<strong>${scan.scan_id}</strong>
				<span>${safe(scan.created_at)} · Qualified ${safe(scan.qualified, 0)} · Grade ${num(scan.avg_premarket_grade, 1)}</span>
			</div>`).join('');
	savedList.querySelectorAll('.saved-item').forEach(item => { item.addEventListener('click', async () => { const scanId = item.dataset.scanId; const response = await fetch(`/api/scans/${scanId}`); const payload = await response.json(); applyPayload(payload); if (sessionStatus) sessionStatus.textContent = `Loaded scan ${scanId}`; }); });
}

async function renderReportsList() {
	const el = document.getElementById('reports-list');
	if (!el) return;
	try {
		const resp = await fetch('/api/scans');
		const data = await resp.json();
		let scans = data.scans || [];
		const query = (reportSearchInput?.value || '').trim().toLowerCase();
		const modeFilter = reportModeFilter?.value || 'all';
		if (query) {
			scans = scans.filter(scan => [scan.scan_id, scan.created_at, scan.scan_mode, scan.message]
				.some(value => String(value || '').toLowerCase().includes(query)));
		}
		if (modeFilter !== 'all') {
			scans = scans.filter(scan => {
				const mode = String(scan.scan_mode || '').toLowerCase();
				if (modeFilter === 'all-stocks') return mode === 'all';
				return mode.includes(modeFilter);
			});
		}
		if (reportsCount) reportsCount.textContent = `${scans.length} report${scans.length === 1 ? '' : 's'}`;
		if (!scans.length) { el.innerHTML = '<div class="empty-state">No saved reports.</div>'; return; }
		el.classList.remove('empty-state');
		el.innerHTML = `<div class="report-list">${scans.map(s => `
			<div class="report-row" data-scan-id="${s.scan_id}">
				<button class="report-summary" type="button" data-action="toggle" data-scan-id="${s.scan_id}">
					<span class="report-name">${safe(s.scan_id)}.json</span>
					<span>${safe(s.created_at)}</span>
					<span class="mode-pill">${modeLabel(s.scan_mode)}</span>
				</button>
				<div class="report-details" hidden>
					<div class="report-metrics">
						<div><span>Symbols</span><strong>${safe(s.symbols_scanned, 0)}</strong></div>
						<div><span>Qualified</span><strong>${safe(s.qualified, 0)}</strong></div>
						<div><span>Grade</span><strong>${num(s.avg_premarket_grade, 1)}</strong></div>
						<div><span>ML</span><strong>${num(s.avg_ml_probability, 1)}</strong></div>
						<div><span>Intraday</span><strong>${safe(s.intraday_ready, 0)}</strong></div>
						<div><span>Swing</span><strong>${safe(s.swing_ready, 0)}</strong></div>
					</div>
					<div class="report-actions">
						<button class="button primary" data-action="open" data-scan-id="${s.scan_id}" type="button">Open report</button>
						<a class="button secondary" href="/api/export/watchlist?scan_id=${encodeURIComponent(s.scan_id)}&horizon=intraday">Intraday CSV</a>
						<a class="button secondary" href="/api/export/watchlist?scan_id=${encodeURIComponent(s.scan_id)}&horizon=swing">Swing CSV</a>
						<a class="button secondary" href="/api/scans/${encodeURIComponent(s.scan_id)}" target="_blank">JSON</a>
					</div>
				</div>
			</div>
		`).join('')}</div>`;

		el.querySelectorAll('[data-action="toggle"]').forEach(btn => btn.addEventListener('click', () => {
			const row = btn.closest('.report-row');
			const details = row?.querySelector('.report-details');
			if (details) details.hidden = !details.hidden;
			row?.classList.toggle('expanded', details && !details.hidden);
		}));
		el.querySelectorAll('[data-action="open"]').forEach(btn => btn.addEventListener('click', async (ev) => {
			ev.preventDefault();
			const sid = btn.dataset.scanId;
			const resp = await fetch(`/api/scans/${sid}`);
			const payload = await resp.json();
			showPage('scan');
			applyPayload(payload);
			setScanState('complete', `Loaded report ${sid}`, 100);
		}));
	} catch (e) { el.innerHTML = '<div class="empty-state">Reports list failed to load.</div>'; }
}

function renderBreadth(breadth) {
	if (!breadth || !Object.keys(breadth).length) { breadthRegion.innerHTML = '<div class="empty-state">Run a scan to display breadth metrics.</div>'; return; }
	const items = [ ['Advancers', breadth.advancers], ['Decliners', breadth.decliners], ['New Highs', breadth.new_highs], ['New Lows', breadth.new_lows], ['Above EMA20', breadth.stocks_above_ema20], ['Above EMA50', breadth.stocks_above_ema50], ['Above EMA200', breadth.stocks_above_ema200], ['Universe', breadth.total_stocks], ];
	breadthRegion.innerHTML = `<div class="metric-grid">${items.map(([label, value]) => `
		<div class="metric-box"><div class="label">${label}</div><div class="value">${safe(value, 0)}</div></div>
	`).join('')}</div>`;
}

function renderSectorHeatmap(rows) {
	if (!rows || !rows.length) { sectorRegion.innerHTML = '<div class="empty-state">Sector leadership will show here after scan.</div>'; return; }
	sectorRegion.innerHTML = `<div class="heatmap" style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;">${rows.map(item => `
		<div class="metric-box" style="background:${pickBackground(item.avg_grade)};">
			<div class="label">${safe(item.sector)}</div>
			<div class="value">${num(item.avg_grade,1)}</div>
			<div class="muted">${safe(item.qualified,0)} qualified</div>
		</div>
	`).join('')}</div>`;
}

function pickBackground(score) { const n = Number(score) || 0; const hue = n >= 0 ? 150 : 10; const alpha = Math.min(Math.abs(n) / 100, 0.75) + 0.08; return `rgba(${hue === 150 ? '82,209,143' : '255,125,116'}, ${alpha})`; }

function renderComparison(comparison) {
	if (!comparison || !comparison.available) { compareRegion.innerHTML = '<div class="empty-state">Need at least two saved scans to compare day-over-day changes.</div>'; return; }
	const sections = [];
	if (comparison.new_entrants?.length) { sections.push(`<div class="metric-box"><div class="label">New Entrants</div>${comparison.new_entrants.map(item => `<div><strong>${item.stock}</strong> · Grade ${num(item.grade_change,1)} · ML ${num(item.ml_change,1)}</div>`).join('')}</div>`); }
	if (comparison.grade_movers?.length) { sections.push(`<div class="metric-box"><div class="label">Grade Movers</div>${comparison.grade_movers.map(item => `<div><strong>${item.stock}</strong> · ${item.direction === 'up' ? '▲' : '▼'} ${num(item.grade_change,1)}</div>`).join('')}</div>`); }
	if (comparison.dropped_setups?.length) { sections.push(`<div class="metric-box"><div class="label">Dropped Setups</div>${comparison.dropped_setups.map(item => `<div><strong>${item.stock}</strong> · Prev ${num(item.previous_grade,1)}</div>`).join('')}</div>`); }
	compareRegion.innerHTML = sections.length ? `<div class="detail-grid">${sections.join('')}</div>` : '<div class="empty-state">No significant changes from prior scan.</div>';
}

function renderHistory(records) {
	// Use Chart.js to render history with zoom/pan
	if (!records?.length) { historyRegion.innerHTML = '<div class="empty-state">Select a stock to view saved scan history.</div>'; return; }
	if (!isChartReady()) { historyRegion.innerHTML = '<div class="empty-state">Chart library unavailable. Refresh or try again later.</div>'; return; }
	const labels = records.map(r => r.created_at || r.scan_id || '');
	const grades = records.map(r => Number(r.premarket_grade || 0));
	const ml = records.map(r => Number(r.ml_probability || 0));
	historyRegion.innerHTML = `<div class="chart-box"><div class="chart-title"><div><strong>${safe(records[0].stock)}</strong> history</div><span>${records.length} points</span></div><canvas id="history-chart" height="220"></canvas><div class="legend"><div class="legend-item">Premarket grade</div><div class="legend-item">ML probability</div></div></div>`;
	const ctx = document.getElementById('history-chart').getContext('2d');
	if (historyChart) historyChart.destroy();
	historyChart = new Chart(ctx, {
		type: 'line',
		data: { labels, datasets: [{ label: 'Premarket Grade', data: grades, borderColor: '#f3b04d', tension: 0.2, fill: false }, { label: 'ML Probability', data: ml, borderColor: '#5fc8b8', tension: 0.2, fill: false }] },
		options: { responsive: true, plugins: { zoom: { pan: { enabled: true, mode: 'x' }, zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'x' } } } }
	});
}

function renderTable(records) {
	if (!records?.length) { tableRegion.innerHTML = '<div class="empty-state">No qualified setups found.</div>'; return; }
	latestRanked = records;
	tableRegion.innerHTML = `<div class="table-shell"><table><thead><tr><th>Rank</th><th>Stock</th><th>Price</th><th>Action</th><th>Horizon</th><th>Grade</th><th>Score</th><th>Conf.</th><th>ML</th><th>Event</th><th>R:R</th></tr></thead><tbody>${records.map((row, index) => `
		<tr data-stock="${row.stock}" class="${activeStock === row.stock ? 'active' : ''}">
			<td>${safe(row.rank, index + 1)}</td>
			<td>${safe(row.stock)}</td>
			<td>${num(priceValue(row), 2)}</td>
			<td><span class="badge ${badgeClass(row.premarket_action || row.trade_type)}">${safe(row.premarket_action || row.trade_type)}</span></td>
			<td>${safe(row.best_horizon)}</td>
			<td>${num(row.premarket_grade,1)}</td>
			<td>${num(row.score,1)}</td>
			<td>${num(row.confidence_pct,1)}</td>
			<td>${num(row.ml_probability,1)}</td>
			<td>${num(row.event_score,1)}</td>
			<td>${num(row.risk_reward,1)}</td>
		</tr>
	`).join('')}</tbody></table></div>`;

	tableRegion.querySelectorAll('tbody tr').forEach(row => { row.addEventListener('click', async () => { const stock = row.dataset.stock; activeStock = stock; renderTable(records); const selected = records.find(r => r.stock === stock); renderDetail(selected); await loadHistory(stock); }); });
}

function renderDetail(stock) {
	if (!stock) { detailRegion.innerHTML = '<div class="empty-state">Select a ranked stock to inspect the setup.</div>'; return; }
	exportIntraday.href = latestPayload?.scan_id ? `/api/export/watchlist?scan_id=${encodeURIComponent(latestPayload.scan_id)}&horizon=intraday` : '#';
	exportSwing.href = latestPayload?.scan_id ? `/api/export/watchlist?scan_id=${encodeURIComponent(latestPayload.scan_id)}&horizon=swing` : '#';

	detailRegion.innerHTML = `
		<div class="metric-grid">
			<div class="metric-box"><div class="label">Stock</div><div class="value">${safe(stock.stock)}</div></div>
			<div class="metric-box"><div class="label">Current price</div><div class="value">${num(priceValue(stock),2)}</div></div>
			<div class="metric-box"><div class="label">Action</div><div class="value">${safe(stock.premarket_action)}</div></div>
			<div class="metric-box"><div class="label">Entry / Stop</div><div class="value">${num(stock.entry,2)} / ${num(stock.stoploss,2)}</div></div>
			<div class="metric-box"><div class="label">Targets</div><div class="value">${num(stock.target1,2)} / ${num(stock.target2,2)}</div></div>
			<div class="metric-box"><div class="label">ML / Confidence</div><div class="value">${num(stock.ml_probability,1)} / ${num(stock.confidence_pct,1)}</div></div>
			<div class="metric-box"><div class="label">Event / Quality</div><div class="value">${num(stock.event_score,1)} / ${num(stock.quality_score,1)}</div></div>
		</div>
	${renderMarketOpenValidation(stock)}
		<div class="metric-box"><div class="label">Premarket notes</div><div>${safe(stock.premarket_reasons)}</div></div>
		<div class="metric-box"><div class="label">Top drivers</div><div>${(stock.top_drivers || []).map(driver => `<div><strong>${safe(driver.module).replace(/_/g, ' ').toUpperCase()}</strong> · ${safe(driver.reason)}</div>`).join('') || '<div>No drivers available.</div>'}</div></div>
	`;

	loadCandlestick(stock.stock);
}

function renderMarketOpenValidation(stock) {
	const validation = stock.market_open_validation || stock.market_open_analysis || {};
	if (!validation || !Object.keys(validation).length) {
		return '';
	}
	const flags = validation.candidate_flags || {};
	return `
		<div class="card">
			<div class="section-head"><div><h3>Market-open validation</h3><strong>${safe(validation.opportunity_classification || validation.classification || 'Validation summary')}</strong></div></div>
			<div class="metric-grid">
				<div class="metric-box"><div class="label">Quality score</div><div class="value">${num(validation.final_trade_quality_score,1)}</div></div>
				<div class="metric-box"><div class="label">Confidence score</div><div class="value">${num(validation.premarket_confidence_score,1)}</div></div>
				<div class="metric-box"><div class="label">Confirmation score</div><div class="value">${num(validation.market_open_confirmation_score,1)}</div></div>
				<div class="metric-box"><div class="label">Opening strength</div><div class="value">${num(validation.opening_strength_pct,2)}%</div></div>
				<div class="metric-box"><div class="label">Order flow</div><div class="value">${num(validation.order_flow_strength,2)}</div></div>
				<div class="metric-box"><div class="label">Volume increase</div><div class="value">${num(validation.relative_volume_increase,2)}%</div></div>
				<div class="metric-box"><div class="label">Acceptance</div><div class="value">${num(validation.price_acceptance_above_key_levels,2)}%</div></div>
			</div>
			<div class="metric-box"><div class="label">Candidate flags</div><div>${Object.entries(flags).map(([key, value]) => `<div>${safe(key.replace(/_/g, ' '))}: <strong>${value ? 'Yes' : 'No'}</strong></div>`).join('')}</div></div>
		</div>
	`;
}

// Render Intraday and Swing lists from latestPayload
function renderIntradayList() {
	const container = document.getElementById('intraday-region');
	if (!container) return;
	let rows = (latestPayload?.ranked || []).filter(r => (r.best_horizon || '').toLowerCase() === 'intraday');
	const q = (document.getElementById('intraday-search')?.value || '').toLowerCase();
	const minG = Number(document.getElementById('intraday-min-grade')?.value || 0);
	const sort = document.getElementById('intraday-sort')?.value || 'grade';
	if(q){ rows = rows.filter(r=> (r.stock||'').toLowerCase().includes(q) || (r.sector||'').toLowerCase().includes(q)); }
	if(minG){ rows = rows.filter(r=> (Number(r.premarket_grade)||0) >= minG); }
	if(sort === 'ml') rows.sort((a,b)=> (Number(b.ml_probability)||0) - (Number(a.ml_probability)||0)); else rows.sort((a,b)=> (Number(b.premarket_grade)||0) - (Number(a.premarket_grade)||0));
	if (!rows.length) { container.innerHTML = '<div class="empty-state">No intraday setups available.</div>'; return; }
	container.innerHTML = `<div class="watchlist-rows">${rows.map(r => `<div class="row-action compact-row"><strong>${r.stock}</strong><div class="small">Price ${num(priceValue(r),2)} | Grade ${num(r.premarket_grade,1)} | ML ${num(r.ml_probability,1)}</div><div class="row-spacer"><a class="secondary" href="#" data-stock="${r.stock}">Open</a></div></div>`).join('')}</div>`;
	container.querySelectorAll('[data-stock]').forEach(a => a.addEventListener('click', (e) => { e.preventDefault(); const s = a.dataset.stock; openStockDetail(s); }));
	// export link
	const exportLink = document.createElement('div'); exportLink.className = 'small'; exportLink.innerHTML = `<a class="button" id="export-intraday-page" href="${latestPayload?.scan_id ? `/api/export/watchlist?scan_id=${encodeURIComponent(latestPayload.scan_id)}&horizon=intraday` : '#'}">Export Intraday</a>`; container.appendChild(exportLink);
}

function renderSwingList() {
	const container = document.getElementById('swing-region');
	if (!container) return;
	let rows = (latestPayload?.ranked || []).filter(r => (r.best_horizon || '').toLowerCase() === 'swing');
	const q = (document.getElementById('swing-search')?.value || '').toLowerCase();
	const minG = Number(document.getElementById('swing-min-grade')?.value || 0);
	const sort = document.getElementById('swing-sort')?.value || 'grade';
	if(q){ rows = rows.filter(r=> (r.stock||'').toLowerCase().includes(q) || (r.sector||'').toLowerCase().includes(q)); }
	if(minG){ rows = rows.filter(r=> (Number(r.premarket_grade)||0) >= minG); }
	if(sort === 'ml') rows.sort((a,b)=> (Number(b.ml_probability)||0) - (Number(a.ml_probability)||0)); else rows.sort((a,b)=> (Number(b.premarket_grade)||0) - (Number(a.premarket_grade)||0));
	if (!rows.length) { container.innerHTML = '<div class="empty-state">No swing setups available.</div>'; return; }
	container.innerHTML = `<div class="watchlist-rows">${rows.map(r => `<div class="row-action compact-row"><strong>${r.stock}</strong><div class="small">Price ${num(priceValue(r),2)} | Grade ${num(r.premarket_grade,1)} | ML ${num(r.ml_probability,1)}</div><div class="row-spacer"><a class="secondary" href="#" data-stock="${r.stock}">Open</a></div></div>`).join('')}</div>`;
	container.querySelectorAll('[data-stock]').forEach(a => a.addEventListener('click', (e) => { e.preventDefault(); const s = a.dataset.stock; openStockDetail(s); }));
	const exportLink = document.createElement('div'); exportLink.className = 'small'; exportLink.innerHTML = `<a class="button" id="export-swing-page" href="${latestPayload?.scan_id ? `/api/export/watchlist?scan_id=${encodeURIComponent(latestPayload.scan_id)}&horizon=swing` : '#'}">Export Swing</a>`; container.appendChild(exportLink);
}

function renderPremarketSummary(payload) {
	if (!payload) return;
	document.getElementById('overview-premarket-qualified').textContent = safe(payload.summary?.qualified, 0);
	document.getElementById('overview-premarket-time').textContent = lastDataFreshness ? lastDataFreshness.toLocaleTimeString() : 'Not run';
}

function renderPremarketOutput() {
	const container = document.getElementById('premarket-output');
	if (!container) return;
	const rows = (latestPayload?.ranked || []).slice(0, 12);
	if (!rows.length) { container.innerHTML = '<div class="empty-state">Run a premarket scan to populate the watchlist.</div>'; return; }
	container.innerHTML = `<div class="table-shell"><table><thead><tr><th>Stock</th><th>Grade</th><th>Action</th><th>Horizon</th></tr></thead><tbody>${rows.map(r => `
		<tr><td>${safe(r.stock)}</td><td>${num(r.premarket_grade,1)}</td><td>${safe(r.premarket_action)}</td><td>${safe(r.best_horizon)}</td></tr>`).join('')}</tbody></table></div>`;
}

function renderCustomList(type) {
	const symbolText = document.getElementById(`${type}-custom-symbols`)?.value || '';
	const region = document.getElementById(`${type}-custom-region`);
	if (!region) return;
	const symbols = symbolText.split(/\s+/).filter(Boolean).map(s => s.toUpperCase());
	if (!symbols.length) { region.innerHTML = '<div class="empty-state">Enter custom symbols to run the scan.</div>'; return; }
	const rows = (latestPayload?.ranked || []).filter(r => symbols.includes((r.stock || '').toUpperCase()) && (type === 'intraday' ? (r.best_horizon || '').toLowerCase() === 'intraday' : (r.best_horizon || '').toLowerCase() === 'swing'));
	if (!rows.length) { region.innerHTML = '<div class="empty-state">No matching results found in the current scan.</div>'; return; }
	region.innerHTML = `<div class="watchlist-rows">${rows.map(r => `<div class="row-action compact-row"><strong>${r.stock}</strong><div class="small">Price ${num(priceValue(r),2)} | Grade ${num(r.premarket_grade,1)} | ML ${num(r.ml_probability,1)}</div><div class="row-spacer"><a class="secondary" href="#" data-stock="${r.stock}">Open</a></div></div>`).join('')}</div>`;
	region.querySelectorAll('[data-stock]').forEach(a => a.addEventListener('click', (e) => { e.preventDefault(); openStockDetail(a.dataset.stock); }));
}

async function loadHistory(stock) { try { const response = await fetch(`/api/history?stock=${encodeURIComponent(stock)}`); const payload = await response.json(); renderHistory(payload.history || []); } catch (error) { historyRegion.innerHTML = '<div class="empty-state">Unable to load stock history.</div>'; } }

async function loadCandlestick(stock) {
	const chartRegion = document.getElementById('chart-region'); if (!chartRegion) return;
	if (!isChartReady()) { chartRegion.innerHTML = '<div class="empty-state">Chart library unavailable. Refresh or try again later.</div>'; return; }
	try {
		const response = await fetch(`/api/candlestick?stock=${encodeURIComponent(stock)}&days=30`);
		const payload = await response.json(); const candles = payload.candles || [];
		if (!candles.length) { chartRegion.innerHTML = '<div class="empty-state">No price data available for this stock.</div>'; return; }

		// Prepare canvas with reset button
		chartRegion.innerHTML = `<div class="chart-title"><div><strong>${stock} price</strong></div><div><button id="reset-zoom" class="secondary">Reset Zoom</button></div></div><canvas id="candlestick-chart" height="260"></canvas>`;
		const ctx = document.getElementById('candlestick-chart').getContext('2d');
		if (candleChart) candleChart.destroy();
		const data = candles.map(c => ({ x: new Date(c.date), o: Number(c.open), h: Number(c.high), l: Number(c.low), c: Number(c.close) }));
		candleChart = new Chart(ctx, {
			type: 'candlestick',
			data: { datasets: [{ label: stock, data }] },
			options: {
				responsive: true,
				plugins: {
					tooltip: {
						enabled: true,
						callbacks: {
							label: function(context) {
								const r = context.raw || context.dataset.data[context.dataIndex];
								if (!r) return '';
								return `O:${r.o}  H:${r.h}  L:${r.l}  C:${r.c}`;
							}
						}
					},
					zoom: { pan: { enabled: true, mode: 'x' }, zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'x' } },
					crosshair: { line: { color: 'rgba(255,255,255,0.12)', width: 1 }, sync: { enabled: false }, zoom: { enabled: false } }
				},
				scales: { x: { type: 'time' }, y: { position: 'right' } }
			}
		});

		// Wire reset button
		const resetBtn = document.getElementById('reset-zoom');
		if (resetBtn) {
			resetBtn.addEventListener('click', () => { try { candleChart.resetZoom(); } catch (e) { console.warn('resetZoom failed', e); } });
		}
	} catch (error) { chartRegion.innerHTML = '<div class="empty-state">Candlestick chart failed to load.</div>'; }
}

// (detailed applyPayload defined below)

// When payload changes, refresh intraday/swing lists too
function applyPayload(payload) {
	latestPayload = payload;
	if (payload?.scan_mode) scanMode = payload.scan_mode;
	activeStock = payload.ranked?.[0]?.stock || payload.results?.[0]?.stock || null;
	updateSummary(payload.summary || {});
	renderSavedScans(payload.saved_scans || []);
	renderBreadth(payload.breadth || {});
	renderSectorHeatmap(payload.sector_heatmap || []);
	renderComparison(payload.comparison || {});
	renderTable(getFilteredRecords(payload.ranked || []));
	renderDetail(latestPayload.ranked?.find(item => item.stock === activeStock) || {});
	if (activeStock) loadHistory(activeStock);
	renderPremarketSummary(payload);
	renderPremarketOutput();
	// populate intraday/swing pages
	renderIntradayList();
	renderSwingList();
}

function updateSummary(summary) { summaryEls.qualified.textContent = safe(summary.qualified, 0); summaryEls.avgGrade.textContent = num(summary.avg_premarket_grade, 1); summaryEls.avgMl.textContent = num(summary.avg_ml_probability, 1); summaryEls.split.textContent = `${safe(summary.intraday_ready, 0)} / ${safe(summary.swing_ready, 0)}`; summaryEls.avgEvent.textContent = num(summary.avg_event_score, 1); reportPath.textContent = latestPayload?.report_path ? latestPayload.report_path : 'Not generated'; }

let currentScanId = null;
let scanPollInterval = null;

function stopPolling() {
	if (scanPollInterval) clearInterval(scanPollInterval);
	scanPollInterval = null;
}

function describeRunningScan(record, statusPayload = {}) {
	const mode = modeLabel(statusPayload.payload?.scan_mode || record?.scan_mode || scanMode);
	const symbols = statusPayload.payload?.auto_nse_universe ? 'full universe' : `${normalizeSymbols(statusPayload.payload?.symbols || record?.payload?.symbols).length || getWatchlistSymbols().length} symbols`;
	return `${mode} scan running (${symbols})`;
}

function handleTerminalScanStatus(status, payload) {
	stopPolling();
	clearActiveScan();
	currentScanId = null;
	if (payload?.payload?.scan_mode) scanMode = payload.payload.scan_mode;
	if (payload?.result?.scan_mode) scanMode = payload.result.scan_mode;
	if (status === 'completed') {
		applyPayload(payload.result || {});
		if (sessionStatus) sessionStatus.textContent = 'Complete';
		setScanState('complete', payload.result?.message || 'Scan complete', 100);
		lastDataFreshness = new Date();
		updateAutoStatus();
		renderReportsList();
		return;
	}
	if (status === 'cancelled' || status === 'cancel_requested') {
		if (sessionStatus) sessionStatus.textContent = 'Cancelled';
		if (tableRegion) tableRegion.innerHTML = '<div class="empty-state">Scan cancelled.</div>';
		setScanState('cancelled', 'Scan cancelled', 0);
		return;
	}
	if (status === 'error') {
		if (sessionStatus) sessionStatus.textContent = 'Error';
		if (tableRegion) tableRegion.innerHTML = `<div class="empty-state">${safe(payload.result?.message || 'Scan failed')}</div>`;
		setScanState('error', payload.result?.message || 'Scan failed', 0);
	}
}

function pollScan(scanId, activeRecord = readActiveScan()) {
	if (!scanId) return;
	currentScanId = scanId;
	if (activeRecord?.scan_mode) scanMode = activeRecord.scan_mode;
	stopPolling();

	const tick = async () => {
		try {
			const st = await fetch(`/api/scan/${scanId}/status`);
			if (!st.ok) throw new Error('Scan session not found');
			const payload = await st.json();
			const status = payload.status;
			if (status === 'running' || status === 'queued') {
				const pct = status === 'queued' ? 8 : runningPercent(activeRecord?.started_at);
				if (sessionStatus) sessionStatus.textContent = `${status === 'queued' ? 'Queued' : 'Running'} (${scanId.slice(0, 6)})`;
				setScanState('running', describeRunningScan(activeRecord, payload), pct);
				return;
			}
			handleTerminalScanStatus(status, payload);
		} catch (error) {
			stopPolling();
			clearActiveScan();
			currentScanId = null;
			if (sessionStatus) sessionStatus.textContent = 'Disconnected';
			setScanState('error', 'Scan session unavailable after refresh', 0);
			console.warn('Status poll error', error);
		}
	};

	tick();
	scanPollInterval = setInterval(tick, 2500);
}

async function startScan() {
	if (currentScanId) {
		showPage('scan');
		setScanState('running', 'A scan is already running', runningPercent(readActiveScan()?.started_at));
		return;
	}
	const formData = getPayloadFromForm();
	console.log('startScan called', formData);
	if (sessionStatus) sessionStatus.textContent = 'Queued';
	setScanState('running', `Starting ${modeLabel(formData.scan_mode)} scan`, 8);
	if (tableRegion) tableRegion.innerHTML = '<div class="empty-state">Queuing scan...</div>';

	try {
		const response = await fetch('/api/scan/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(formData) });
		if (!response.ok) throw new Error('Failed to start scan');
		const json = await response.json();
		currentScanId = json.scan_id;
		saveActiveScan(currentScanId, formData);
		if (sessionStatus) sessionStatus.textContent = `Running (${currentScanId.slice(0,6)})`;
		pollScan(currentScanId, readActiveScan());
	} catch (error) {
		console.error('Scan start failed', error);
		if (sessionStatus) sessionStatus.textContent = 'Error';
		setScanState('error', 'Scan failed to start', 0);
		if (tableRegion) tableRegion.innerHTML = `<div class="empty-state">${safe(error.message)}</div>`;
		// Fallback: try synchronous scan endpoint if background start fails
		try {
			const resp = await fetch('/api/scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(formData) });
			if (resp.ok) {
				const payload = await resp.json();
				applyPayload(payload);
					if (sessionStatus) sessionStatus.textContent = 'Complete';
					setScanState('complete', payload.message || 'Ready', 100);
				lastDataFreshness = new Date();
				updateAutoStatus();
			} else {
				console.error('Fallback synchronous scan failed', resp.statusText);
			}
		} catch (e) {
			console.warn('Fallback scan failed', e);
		}
	}
}

async function stopScan() {
	if (!currentScanId) {
		setScanState('idle', 'No active scan to stop', 0);
		return;
	}
	try {
		const resp = await fetch('/api/scan/stop', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scan_id: currentScanId }) });
		const payload = await resp.json();
		if (payload.status === 'ok') {
			if (sessionStatus) sessionStatus.textContent = 'Stopping';
			setScanState('running', payload.message || 'Stopping scan', runningPercent(readActiveScan()?.started_at));
		}
	} catch (e) { console.warn('Stop failed', e); }
}

function updateAutoStatus() {
	if (!autoRefreshInput || !autoStatus) return;
	if (autoRefreshTimer) clearInterval(autoRefreshTimer);
	if (!autoRefreshInput.checked) {
		autoStatus.textContent = 'Auto-refresh off';
		return;
	}
	const minutes = Math.max(Number(refreshMinutesInput.value) || 5, 1);
	autoStatus.textContent = `Auto refresh every ${minutes}m`;
	autoRefreshTimer = setInterval(() => {
		if (!autoRefreshInput.checked || currentScanId) return;
		startScan();
	}, minutes * 60 * 1000);
}

async function initDashboard() {
	// wire toolbar controls (search, filters, sort, page size)
	const tableSearch = document.getElementById('table-search');
	const tableHorizonFilter = document.getElementById('table-horizon-filter');
	const tableSort = document.getElementById('table-sort');
	const pageSize = document.getElementById('page-size');
	const intradaySearch = document.getElementById('intraday-search');
	const intradayMinGrade = document.getElementById('intraday-min-grade');
	const swingSearch = document.getElementById('swing-search');
	const swingMinGrade = document.getElementById('swing-min-grade');

	// attach events
	if(tableSearch) tableSearch.addEventListener('input', debounce(()=>{ renderTable(getFilteredRecords(latestPayload?.ranked || [])); }, 200));
	if(tableHorizonFilter) tableHorizonFilter.addEventListener('change', ()=>{ renderTable(getFilteredRecords(latestPayload?.ranked || [])); });
	if(tableSort) tableSort.addEventListener('change', ()=>{ renderTable(getFilteredRecords(latestPayload?.ranked || [])); });
	if(pageSize) pageSize.addEventListener('change', ()=>{ renderTable(getFilteredRecords(latestPayload?.ranked || [])); });
	if(intradaySearch) intradaySearch.addEventListener('input', debounce(()=>{ renderIntradayList(); },200));
	if(intradayMinGrade) intradayMinGrade.addEventListener('change', ()=>{ renderIntradayList(); });
	if(swingSearch) swingSearch.addEventListener('input', debounce(()=>{ renderSwingList(); },200));
	if(swingMinGrade) swingMinGrade.addEventListener('change', ()=>{ renderSwingList(); });

	form = document.getElementById('scan-form');
	savedList = document.getElementById('saved-list');
	tableRegion = document.getElementById('table-region');
	detailRegion = document.getElementById('detail-region');
	breadthRegion = document.getElementById('breadth-region');
	sectorRegion = document.getElementById('sector-region');
	compareRegion = document.getElementById('compare-region');
	historyRegion = document.getElementById('history-region');
	sessionStatus = document.getElementById('session-status');
	progressState = document.getElementById('progress-state');
	reportPath = document.getElementById('report-path');
	autoStatus = document.getElementById('auto-status');
	exportIntraday = document.getElementById('export-intraday');
	exportSwing = document.getElementById('export-swing');
	exportCurrentCsvBtn = document.getElementById('export-current-csv');
	intradayExportCsvBtn = document.getElementById('intraday-export-csv');
	swingExportCsvBtn = document.getElementById('swing-export-csv');
	compareReportsBtn = document.getElementById('compare-reports');
	loadDemo = document.getElementById('load-demo');
	scanWatchlist = document.getElementById('scan-watchlist');
	scanAll = document.getElementById('scan-all');
	scanNow = document.getElementById('scan-now');
	heroScanWatchlist = document.getElementById('hero-scan-watchlist');
	heroScanAll = document.getElementById('hero-scan-all');
	heroScanNow = document.getElementById('hero-scan-now');
	autoRefreshInput = document.getElementById('auto_refresh');
	refreshMinutesInput = document.getElementById('refresh_minutes');
	premarketRunBtn = document.getElementById('premarket-run');
	premarketCustomRunBtn = document.getElementById('premarket-custom-run');
	intradayCustomRunBtn = document.getElementById('intraday-custom-run');
	swingCustomRunBtn = document.getElementById('swing-custom-run');
	saveSettingsBtn = document.getElementById('save-settings');
	watchlistEditor = document.getElementById('watchlist-editor');
	watchlistPreview = document.getElementById('watchlist-preview');
	watchlistCount = document.getElementById('watchlist-count');
	saveWatchlistBtn = document.getElementById('save-watchlist');
	applyWatchlistBtn = document.getElementById('apply-watchlist');
	resetWatchlistBtn = document.getElementById('reset-watchlist');
	saveStrategyBtn = document.getElementById('save-strategy');
	loadStrategyBtn = document.getElementById('load-strategy');
	deleteStrategyBtn = document.getElementById('delete-strategy');
	refreshStrategiesBtn = document.getElementById('refresh-strategies');
	advancedScanPanel = document.getElementById('advanced-scan-panel');
	advancedSettingsToggle = document.getElementById('toggle-advanced-settings');
	toggleIntradayCustomBtn = document.getElementById('toggle-intraday-custom');
	toggleSwingCustomBtn = document.getElementById('toggle-swing-custom');
	intradayCustomPanel = document.getElementById('intraday-custom-panel');
	swingCustomPanel = document.getElementById('swing-custom-panel');
	scanStatusCard = document.getElementById('scan-status-card');
	scanProgressFill = document.getElementById('scan-progress-fill');
	scanProgressLabel = document.getElementById('scan-progress-label');
	scanProgressPercent = document.getElementById('scan-progress-percent');
	scanStageList = document.getElementById('scan-stage-list');
	reportSearchInput = document.getElementById('report-search');
	reportModeFilter = document.getElementById('report-mode-filter');
	reportsCount = document.getElementById('reports-count');
	pinnedScan = document.getElementById('pinned-scan');
	pinnedScanTitle = document.getElementById('pinned-scan-title');
	pinnedScanSubtitle = document.getElementById('pinned-scan-subtitle');
	marketTime = document.getElementById('market-time');
	marketStatus = document.getElementById('market-status');
	intradayCurrentStatus = document.getElementById('intraday-current-status');
	intradayProgressFill = document.getElementById('intraday-progress-fill');
	intradayRecentType = document.getElementById('intraday-recent-type');
	swingCurrentStatus = document.getElementById('swing-current-status');
	swingProgressFill = document.getElementById('swing-progress-fill');
	swingRecentType = document.getElementById('swing-recent-type');

	console.log('dashboard initialization starting');

	if (form) {
		form.addEventListener('submit', event => { event.preventDefault(); console.log('form submit triggered'); showPage('scan'); startScan(); updateAutoStatus(); });
	} else {
		console.warn('Scan form not found at initialization');
	}

	if (autoRefreshInput) autoRefreshInput.addEventListener('change', updateAutoStatus);
	if (refreshMinutesInput) refreshMinutesInput.addEventListener('change', updateAutoStatus);

	if(scanWatchlist) scanWatchlist.addEventListener('click', runWatchlistScan);
	if(scanAll) scanAll.addEventListener('click', runFullScan);
	if(scanNow) scanNow.addEventListener('click', runNow);
	const stopScanBtn = document.getElementById('stop-scan');
	if (stopScanBtn) stopScanBtn.addEventListener('click', stopScan);
	if(heroScanWatchlist) heroScanWatchlist.addEventListener('click', runWatchlistScan);
	if(heroScanAll) heroScanAll.addEventListener('click', runFullScan);
	if(heroScanNow) heroScanNow.addEventListener('click', runNow);
	if(loadDemo) loadDemo.addEventListener('click', () => setSymbolsTextarea(getWatchlistSymbols()));
	if(advancedSettingsToggle) advancedSettingsToggle.addEventListener('click', toggleAdvancedSettings);
	if(toggleIntradayCustomBtn) toggleIntradayCustomBtn.addEventListener('click', toggleIntradayCustomScan);
	if(toggleSwingCustomBtn) toggleSwingCustomBtn.addEventListener('click', toggleSwingCustomScan);
	if(premarketRunBtn) premarketRunBtn.addEventListener('click', runPremarketScan);
	if(premarketCustomRunBtn) premarketCustomRunBtn.addEventListener('click', runPremarketCustomScan);
	if(intradayCustomRunBtn) intradayCustomRunBtn.addEventListener('click', runIntradayCustomScan);
	if(swingCustomRunBtn) swingCustomRunBtn.addEventListener('click', runSwingCustomScan);
	if(saveSettingsBtn) saveSettingsBtn.addEventListener('click', saveSettings);
	if(saveStrategyBtn) saveStrategyBtn.addEventListener('click', saveStrategy);
	if(loadStrategyBtn) loadStrategyBtn.addEventListener('click', loadStrategy);
	if(deleteStrategyBtn) deleteStrategyBtn.addEventListener('click', deleteStrategy);
	if(refreshStrategiesBtn) refreshStrategiesBtn.addEventListener('click', async () => { await fetchStrategies(); setScanState('idle', 'Strategies refreshed', 0); });
	if(watchlistEditor) watchlistEditor.addEventListener('input', renderWatchlistEditor);
	if(saveWatchlistBtn) saveWatchlistBtn.addEventListener('click', () => saveWatchlist(true));
	if(applyWatchlistBtn) applyWatchlistBtn.addEventListener('click', applyWatchlistToForm);
	if(resetWatchlistBtn) resetWatchlistBtn.addEventListener('click', resetWatchlist);
	if(reportSearchInput) reportSearchInput.addEventListener('input', debounce(renderReportsList, 200));
	if(reportModeFilter) reportModeFilter.addEventListener('change', renderReportsList);
	if(compareReportsBtn) compareReportsBtn.addEventListener('click', async () => { showPage('reports'); await renderReportsList(); });
	if(exportCurrentCsvBtn) exportCurrentCsvBtn.addEventListener('click', () => downloadCsv(getCurrentCsvRows(), 'ranked-setups.csv'));
	if(intradayExportCsvBtn) intradayExportCsvBtn.addEventListener('click', () => { if (!latestPayload?.scan_id) { alert('Run a scan first before exporting intraday results.'); return; } window.open(`/api/export/watchlist?scan_id=${encodeURIComponent(latestPayload.scan_id)}&horizon=intraday`, '_blank'); });
	if(swingExportCsvBtn) swingExportCsvBtn.addEventListener('click', () => { if (!latestPayload?.scan_id) { alert('Run a scan first before exporting swing results.'); return; } window.open(`/api/export/watchlist?scan_id=${encodeURIComponent(latestPayload.scan_id)}&horizon=swing`, '_blank'); });

	if (!scanWatchlist || !scanAll || !scanNow) {
		console.warn('Scan action buttons missing', { scanWatchlist, scanAll, scanNow });
	}

	updateModeButtons();
	renderMarketClock();
	setInterval(renderMarketClock, 1000);
	updatePinnedScan('idle', 'No active scan', 'Recent scan: None');
	await loadSettings();
	await fetchStrategies();
	loadWatchlistEditor();
	await fetchSavedScans();
	await renderReportsList();
	updateAutoStatus();

	// Wire page navigation buttons after DOM ready
	document.querySelectorAll('.nav-btn').forEach(btn => {
		btn.addEventListener('click', (e) => {
			const page = btn.dataset.page;
			showPage(page);
		});
	});

	// Show initial page based on hash (support deep links like #scan/RELIANCE.NS)
	const initialHash = (location.hash || '#overview').slice(1);
	const [initialPage, initialParam] = initialHash.split('/');
	showPage(initialPage || 'overview', initialParam);
	const activeScan = readActiveScan();
	if (activeScan?.scan_id) {
		showPage('scan');
		pollScan(activeScan.scan_id, activeScan);
	}
}

function onReady(fn) {
	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', fn);
	} else {
		fn();
	}
}

onReady(initDashboard);

// Fallback delegation to ensure buttons respond even if direct handlers failed
function finishHandledClick(e) {
	e.preventDefault();
	e.stopImmediatePropagation();
}

document.addEventListener('click', function(e) {
	const btn = e.target.closest && e.target.closest('button, a');
	if (!btn) return;
	const id = btn.id || btn.dataset.action || '';
	// nav buttons
	if (btn.classList.contains('nav-btn') || btn.dataset.page) {
		const page = btn.dataset.page || btn.getAttribute('data-page');
		if (page) { showPage(page); finishHandledClick(e); return; }
	}
	// quick scan actions
	if (id === 'scan-now' || btn.id === 'hero-scan-now') { runNow(); finishHandledClick(e); return; }
	if (id === 'scan-watchlist' || btn.id === 'hero-scan-watchlist') { runWatchlistScan(); finishHandledClick(e); return; }
	if (id === 'scan-all' || btn.id === 'hero-scan-all') { runFullScan(); finishHandledClick(e); return; }
	if (id === 'stop-scan') { stopScan(); finishHandledClick(e); return; }
	if (id === 'load-demo') { setSymbolsTextarea(getWatchlistSymbols()); finishHandledClick(e); return; }
	// premarket / custom
	if (id === 'premarket-run') { runPremarketScan(); finishHandledClick(e); return; }
	if (id === 'premarket-custom-run') { runPremarketCustomScan(); finishHandledClick(e); return; }
	if (id === 'intraday-custom-run') { runIntradayCustomScan(); finishHandledClick(e); return; }
	if (id === 'swing-custom-run') { runSwingCustomScan(); finishHandledClick(e); return; }
	// settings and reports
	if (id === 'save-settings') { saveSettings(); finishHandledClick(e); return; }
	if (id === 'compare-reports') { showPage('reports'); renderReportsList(); finishHandledClick(e); return; }
	if (id === 'export-current-csv') { downloadCsv(getCurrentCsvRows(), 'ranked-setups.csv'); finishHandledClick(e); return; }
}, true);

console.log('dashboard delegation installed (v3)');
// Simple client-side routing for pages with optional param (e.g. stock ticker)
function showPage(page, param) {
	document.querySelectorAll('.page').forEach(el => { el.classList.remove('active'); el.style.display = 'none'; });
	const el = document.getElementById('page-' + page);
	if (el) { el.classList.add('active'); el.style.display = 'block'; }
	document.querySelectorAll('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.page === page));
	try { history.replaceState({}, '', param ? `#${page}/${encodeURIComponent(param)}` : `#${page}`); } catch (e) {}

	// If a stock param passed for scan page, open its detail
	if (page === 'scan' && param) {
		const stock = decodeURIComponent(param);
		openStockDetail(stock);
	}
}

// Open a specific stock detail (uses latestPayload if available)
async function openStockDetail(stock) {
	if (!stock) return;
	// Ensure scan page visible
	showPage('scan');
	// If latestPayload present, find the stock
	if (latestPayload) {
		const found = (latestPayload.ranked || []).find(r => r.stock === stock) || (latestPayload.results || []).find(r => r.stock === stock);
		if (found) {
			activeStock = stock;
			renderTable(latestPayload.ranked || []);
			renderDetail(found);
			await loadHistory(stock);
			return;
		}
	}

	// Fallback: try to fetch saved scans and search them
	try {
		const scansResp = await fetch('/api/scans');
		const scansJson = await scansResp.json();
		for (const s of scansJson.scans || []) {
			const resp = await fetch(`/api/scans/${s.scan_id}`);
			const payload = await resp.json();
			const found = (payload.ranked || []).find(r => r.stock === stock) || (payload.results || []).find(r => r.stock === stock);
			if (found) {
				applyPayload(payload);
				activeStock = stock;
				renderDetail(found);
				await loadHistory(stock);
				return;
			}
		}
	} catch (e) {
		console.warn('deep-link search failed', e);
	}
}
