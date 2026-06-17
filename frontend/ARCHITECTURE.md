# Trading Terminal Frontend Architecture

## Vision

Build a premium institutional-grade frontend for the scanner platform with a command center experience. The UI must feel like a trading terminal: dense, data-rich, fast, and configurable, while remaining clean and usable across desktop, tablet, and mobile.

## High-Level UX Architecture

### Global Shell
- Persistent top header with key market and system widgets.
- Left-hand primary navigation for pages and workflow anchors.
- Central content area for page-specific command center experiences.
- Right-hand contextual tray for active scan details, alerts, and quick actions.
- Bottom toast/notification bar for system messages.

### Page Categories
1. Dashboard
2. Premarket Analysis
3. Intraday Scanner
4. Swing Scanner
5. Scan Center
6. Reports Center
7. Watchlist
8. Settings

### Interaction patterns
- Card-based sections with collapsible sub-panels.
- Sticky chart summary tray for each page.
- Single source of truth for real-time market state.
- Drag-and-drop grouping and table card reordering.
- In-page quick action strips for push-to workflows.

## Component Hierarchy

### Atoms
- `Button`
- `Badge`
- `Card`
- `IconButton`
- `Input`
- `Select`
- `Switch`
- `Spinner`
- `Tooltip`
- `ProgressBar`
- `Pill`
- `Chip`

### Molecules
- `MetricTile`
- `StockTicker`
- `ScoreBadge`
- `StockPriceBadge`
- `FilterRow`
- `SearchInput`
- `SortableTableHeader`
- `MiniKpiPanel`
- `StockCardHeader`
- `ScanStatusChip`
- `InfoTooltip`

### Organisms
- `GlobalHeader`
- `MarketStatusStrip`
- `LiveIndexPanel`
- `ScanProgressPanel`
- `DashboardGrid`
- `StockCardGrid`
- `PremarketScanCanvas`
- `DualPanelScanner`
- `ReportGallery`
- `SettingsAccordion`
- `WatchlistTable`
- `ScanControlConsole`
- `AdvancedFilterDrawer`
- `EventTimeline`
- `ComparisonMatrix`

### Pages
- `DashboardPage`
- `PremarketPage`
- `IntradayPage`
- `SwingPage`
- `ScanCenterPage`
- `ReportsPage`
- `WatchlistPage`
- `SettingsPage`

## Folder Structure

frontend/
  package.json
  tsconfig.json
  next-env.d.ts
  README.md
  ARCHITECTURE.md
  src/
    app/
      layout.tsx
      page.tsx
      globals.css
    components/
      atoms/
      molecules/
      organisms/
      layout/
    lib/
      api.ts
      websocket.ts
      config.ts
      types.ts
      notifications.ts
    hooks/
      useApi.ts
      useRealtime.ts
      useToast.ts
      useDarkMode.ts
      useDebounce.ts
    state/
      store.ts
      dashboardSlice.ts
      scanSlice.ts
      watchlistSlice.ts
      settingsSlice.ts
    styles/
      variables.css
      layout.css
      cards.css
      responsive.css
    utils/
      dataFormatter.ts
      errorMapper.ts
      uiHelpers.ts

## Dashboard Wireframe Layout

### Header
- Global top bar with brand, navigation, search, theme toggle, profile menu.
- Widget strip pinned below header with live market status and scan telemetry.

### Primary dashboard sections
- `Premarket Recommendations` (hero cards)
- `Intraday Opportunities` (stock card grid)
- `Swing Opportunities` (stock card grid)
- `Recently Completed Scans` (timeline/list)
- `Active Scans` (progress & heatmap)
- `Top ML Scored Stocks` (ranking table)
- `High Confidence Trades` (priority cards)
- `Watchlist Alerts` (alert feed)
- `Market Sentiment` (sentiment barometer and news ticker)

### Stock card layout
- Header: Stock name, NSE symbol, sector, recommendation pill.
- Row 1: Current live price, entry, stop loss, T1/T2/T3.
- Row 2: Risk/reward, ML score, technical score, fundamental score, confidence.
- Row 3: Volume strength, breakout strength, pattern, trend, timestamps.
- Footer: action buttons: pin/watchlist, push intraday/swing, compare, analysis, export.
- Expandable details panel with technical summary, news impact, validation checks.

### Responsive behavior
- Desktop: 4-column dashboard grid and a sticky right-side summary column.
- Tablet: 2-column grid with collapsed charts and drawer-based detail panels.
- Mobile: single-column flow with collapsible sections and floating quick action bar.

## Responsive Layout Plan

### Breakpoints
- `xl` ≥ 1600px: full command center, 4+ dashboard columns.
- `lg` 1200px–1600px: 3-column layout, persistent widget strip.
- `md` 900px–1200px: 2-column layout, contextual drawers.
- `sm` 640px–900px: stacked cards, collapsible filters.
- `xs` < 640px: mobile-first cards, bottom navigation, transient modals.

### Adaptive interactions
- Tables become card lists on small screens.
- Large filters move into an overlay panel.
- Market widget strip collapses into a carousel or expandable drawer.
- Stock actions move to sticky footer on mobile.

## State Management Design

### Strategy
- Use Redux Toolkit for shared application state and workflow orchestration.
- Use SWR or React Query for API data fetching, caching, and real-time refresh.
- Use local UI state hooks for filter drawers, modal state, and expanded card panels.
- Use a central `RealtimeService` for live market feed and scan events.

### Slice responsibilities
- `dashboardSlice` — summary metrics, hero datasets, sentiment state.
- `scanSlice` — active scan queue, progress, selected scan, scan history.
- `watchlistSlice` — pinned symbols, alerts, watchlist metadata.
- `settingsSlice` — UI preferences, theme, module toggles.
- `marketSlice` — live index values, market status, feed health.

### Data access flow
- Pages query API endpoints through typed adapters in `src/lib/api.ts`.
- `store` contains normalized objects for stocks, scans, reports, settings.
- Real-time events update store via dispatch actions for market updates and scan progress.

## API Integration Strategy

### Service layer
- `src/lib/api.ts` exposes typed fetchers:
  - `getHealth()`
  - `startScan(payload)`
  - `stopScan(scanId)`
  - `getScanStatus(scanId)`
  - `listScans()`
  - `getScanDetail(scanId)`
  - `getHistory()`
  - `getSettings()`
  - `saveSettings(payload)`
  - `getStrategies()`
  - `getMarketOpenAnalysis()`
  - `getCandlestickData()`
  - `exportWatchlist()`

### Data adapter patterns
- Use response normalizers to map backend records to frontend contract.
- Add fallback values and typed fields for missing legacy properties.
- Keep backend contract stable by using a single `api.ts` adapter layer.

### Polling and subscription
- On Dashboard and Scanner pages, start interval refreshes for slow data and metrics.
- Use stable event sources for fast updates (market ticks, progress, health state).
- Provide explicit `Refresh` actions and `Live` toggle switches.

## Loading States

### Principles
- Always show skeleton UI before data appears.
- Keep overall layout stable during load transitions.
- Use lightweight shimmer cards for stock card grids.
- Keep `refreshing` spin indicator on header widgets during background refresh.

### Page-level states
- `dashboard` — hero skeletons, list placeholders, widget skeleton stripes.
- `premarket` — filter panel loader, scan canvas placeholder, comparison chart skeleton.
- `scan center` — queue panel with progress placeholders.
- `reports` — card list loader and preview skeleton.
- `settings` — form skeleton for module panels.

## Error Handling Strategy

### Global layer
- Top-level `ErrorBoundary` for rendering fallback UI if page runtime fails.
- Notification system presents errors with context and retry action.

### API errors
- Capture API status in `lib/api.ts` and return typed error objects.
- Show inline errors on filter panels and tables.
- Recover by retrying non-destructive operations automatically when safe.
- Present backend health issues as a persistent banner in the global header.

### User feedback
- Use toast categories: success, warning, error, info.
- Add contextual retry buttons and error details for advanced users.
- For scanning failures, attach `scan_id`, issue message, and telemetry link.

## Notification System

### Components
- `ToastProvider` / `ToastStack`
- `InlineBanner`
- `AlertFlyout`
- `MarketEventTicker`

### Event sources
- Scan lifecycle: queued, running, paused, completed, failed.
- Market health: feed disconnect, API latency, stale data.
- User actions: saved settings, pushed stock, export complete.

### UX rules
- Use non-blocking toasts for routine updates.
- Use modal confirmation only for destructive operations.
- Keep action-focused messages with `Undo` or `Retry`.

## Real-Time Event Architecture

### Push model
- Primary transport: WebSocket connection to backend at `/ws` or `/events`.
- Secondary fallback: polling endpoint `api/scan/{scan_id}/status`.

### Event payloads
- `market-tick` — index prices, market breadth, feed health, time.
- `scan-progress` — scan_id, status, stage, processed, remaining.
- `scan-result` — latest scan payload, qualified count, action summary.
- `stock-update` — live price, bid/ask, volume strength, breakout state.
- `alert` — watchlist warning, market sentiment change.

### Client architecture
- `RealtimeService` manages connect/disconnect/reconnect.
- `useRealtime` hook subscribes to event types and maps them to store actions.
- `EventBus` normalizes browser events for UI components.
- `LiveMode` toggles between push updates and periodic refresh.

## WebSocket Architecture

### Service outline
- Connect to `ws://localhost:5000/ws` or `wss://<host>/ws`.
- Emit `subscribe` messages for `market`, `scan`, `stocks`, `alerts`.
- Reconnect with exponential backoff.
- Monitor latency and stale state.

### Message types
- `connection.ack`
- `market.snapshot`
- `scan.update`
- `stock.tick`
- `stock.alert`
- `system.health`

### UI integration
- Use WebSocket events to update global widget strip.
- Use snapshot events to keep Dashboard and Scanner sections in sync.
- Use delta events to reduce bandwidth for high-frequency price updates.

## UI Component Library Structure

### Shared design tokens
- `primary`, `secondary`, `warning`, `danger`, `success`
- `bg-dark`, `bg-surface`, `text-high`, `text-muted`
- spacing scale, border radius, shadows, motion ease

### Reusable component patterns
- `Card` with theme-aware border and elevation
- `MetricTile` for top-line score values
- `StatusBadge` for BUY / SELL / HOLD / WATCH
- `StockTimeline` for price vs. target validation
- `ComparisonMatrix` for premarket vs open vs current
- `FilterPanel` with saved layouts and presets
- `TabbedPanel` for page-level segment switching
- `ChartCard` for analytics with a built-in legend

## Page Designs

### Dashboard
- Command center with hero metrics and live market strip.
- `Premarket Recommendations` hero cards and prioritized stock grid.
- `Intraday Opportunities` quick view of names pushed from Premarket.
- `Swing Opportunities` intermediate horizon with breakout and trend signals.
- `Recently Completed Scans` timeline with scan status, accuracy, and result summary.
- `Active Scans` progress dashboard with ETA, stage, CPU/memory, API usage.
- `Top ML Scored Stocks` ranked grid with score badges and confidence bar.
- `High Confidence Trades` curated watchlist of top 8 setups.
- `Watchlist Alerts` live feed of triggered watchlist events.
- `Market Sentiment` dial, news sentiment indicator, and sector rotation.

### Premarket Analysis
- Full scan control region with universe selection and sector/industry selectors.
- Workflow cards for Gap Up/Down, Volume, News, Earnings, Sector Rotation, Relative Strength, Option Chain, ML.
- Post-Premarket validation dashboard at 9:08 AM and market open.
- Comparison matrix for Expected Price vs 9:08 vs Open vs Current.
- Validation gauges: prediction accuracy, confidence change, trend/volume/entry/stop confirmation.
- One-click push actions to Dashboard, Intraday, Swing, Watchlist.
- Visual analytics with bar/area charts and scatter comparisons.

### Intraday / Swing Pages
- Dual-panel layout:
  - Left: premarket qualified stocks pushed into the scanner.
  - Right: manual custom scan canvas and filter panels.
- Live price ticker, P&L tracking, multi-timeframe indicator summary.
- Breakout detection, support/resistance scoreboard, pattern detection.
- Stock actions: highlight, star, pin, list move, compare, analysis.
- Advanced filters for sector, industry, market cap, volume, price, ML/tech/risk.
- Toggle between grid and card view, and TradingView-style chart layout.

### Scan Center
- Control room for all scans and schedules.
- Scan queue list, active/pending/failed/completed sections.
- Ability to start/pause/resume/stop scans with priority tags.
- Recurring scan builder with calendar schedule and templates.
- Real-time dashboards showing progress, ETA, stocks processed, remaining, stage.
- Telemetry panel for API usage, CPU, memory, feed health.

### Reports Center
- Report catalog with categories, search, tags, and quick preview.
- Hover cards reveal report summary, accuracy, confidence, and coverage.
- Compare reports side-by-side with special view for Premarket vs 9:08 vs Open vs EOD.
- Download PDF/Excel, compare, share, archive.
- Analytics panel with prediction accuracy, false positives, false negatives, best/worst indicators.

### Watchlist
- Pinned watchlist timeline with alerts and live quotes.
- Instant push to scan, dashboard, intraday, swing.
- Watchlist card view with score summary and signal triggers.
- Alerts timeline with breaking events, news, and technical triggers.

### Settings
- Modular accordion UI for configuration categories.
- Each module includes enable/disable, thresholds, weights, frequency, rules, and confidence limits.
- Save, import/export, version history, rollback, reset defaults.
- Real-time backend sync and validation from the settings API.

## Compatibility with Current Backend

### Keep backend unchanged
- The new frontend sits on top of the existing Python `ui/app.py` APIs.
- No backend business logic changes are required.
- The UI integration layer maps legacy payload shapes into the new dashboard contract.

### Backend extension points
- Add WebSocket endpoint in backend later for market live state.
- Add dedicated JSON summary endpoints for dashboard metrics if needed.

## Implementation Priorities

1. Build `GlobalHeader` and widget strip.
2. Build core `DashboardPage` with hero metrics and stock card grid.
3. Add `PremarketPage` with scan control and comparison dashboard.
4. Add `ScanCenterPage` with queue and progress panels.
5. Add `ReportsPage` with catalog and preview.
6. Add `SettingsPage` with configuration modules.
7. Add `WatchlistPage` plus `IntradayPage` / `SwingPage` dual-panel flows.
8. Add real-time WebSocket fallback and live updates.

## Notes
- Use modular CSS variables and `prefers-color-scheme` for theme.
- Build all card components to support collapsed/expanded states.
- Design for high-density data display without sacrificing clarity.
- Ensure keyboard navigation and screen reader compatibility across panels.
