# Real-Time Stock Intelligence Platform Architecture

## Product Description

Scanner is an NSE-focused real-time stock intelligence platform. Its goal is to move live market data through backend analysis engines, scanner-specific opportunity filters, AI/ML validation, risk checks, meta ranking, alerts, and a premium dashboard without showing dummy values or forcing the user to wait for heavy work at page-load time.

The product standard is:

- Live data first: no hardcoded market values or fake rankings.
- Scanner ownership: each scanner has a dedicated purpose and output contract.
- Strict decisions: prefer `No Trade` or `Watch Only` over weak opportunities.
- Fast UI: pages read cached/latest results, then refresh in the background.
- Explainability: every opportunity should include score, reason, risk, entry, stop, and target context.

## Current Runtime

- Frontend: Next.js 14, React, TypeScript, Redux, polling fallback, premium dark UI.
- Backend: Python aiohttp service on port `5000`.
- Local store: SQLite in `ui/data/v20.sqlite`.
- Market adapter: `MarketDataProvider` abstraction with Yahoo Finance implementation.
- Reports: Excel and JSON scan reports under `ui/data` and report output folders.
- Alerts: backend alert records plus Telegram delivery integration where credentials are configured.

## Target Production Runtime

- Frontend: Next.js deployed behind HTTPS.
- API gateway: aiohttp/FastAPI-compatible backend routes with typed response contracts.
- Persistent store: PostgreSQL.
- Hot cache: Redis sorted sets and hashes for quotes, rankings, breadth, alerts, and AI/ML snapshots.
- Workers: background scan and ingestion workers, separated from user request/response paths.
- Streaming: WebSocket or SSE for quote updates, scanner updates, alert events, and freshness state.

## End-to-End Data Flow

1. Market provider adapter fetches quotes, candles, financial metrics, indices, sector data, and news.
2. Ingestion service validates symbols, timestamps, provider source, and freshness.
3. Hot cache stores latest quotes, top rankings, watchlist quote state, breadth, and sector snapshots.
4. Persistent store records candles, indicators, scanner runs, scanner results, AI/ML decisions, alerts, reports, and audit logs.
5. Indicator engine updates VWAP, EMA, RSI, MACD, ADX, ATR, supertrend, relative volume, sector strength, and breadth.
6. Scanner services produce scan-type-specific candidates.
7. Risk, backtest, ML, AI, and Meta Scanner layers validate candidates.
8. Final Decision Engine returns `Strong Opportunity`, `Opportunity`, `Watch Only`, `Avoid`, or `No Trade`.
9. Frontend reads latest cached result immediately and keeps refreshing/streaming freshness state.

## Scanner Ownership

- Premarket: gap, pre-open momentum, news, relative volume, sector context, and market-open readiness.
- Open Confirmation: validates only premarket shortlisted names around the configured market-open time.
- Intraday: same-day trade setups using live price, VWAP, volume, momentum, breadth, and risk.
- Swing: multi-day setups using daily trend, fundamentals, support/resistance, risk reward, and quality.
- Groww: retail-source import that resolves symbols and runs intraday analysis on the resolved list.
- Meta Scanner: combines scanner evidence and flags agreement/conflict.
- Final Decision: strict post-meta gate that decides show/trade/watch/reject.

## API Contract

Canonical routes now available:

- `GET /api/dashboard/live`
- `GET /api/scanners/{scan_type}/latest`
- `GET /api/meta-scanner/latest`
- `GET /api/stocks/{symbol}/analysis`
- `GET /api/stocks/{symbol}/trade-plan`
- `GET /api/ai/insights/{symbol}`
- `GET /api/ml/predictions/{symbol}`
- `GET /api/watchlist`
- `POST /api/watchlist`
- `GET /api/alerts`
- `POST /api/alerts`

Existing V20 routes remain available for compatibility.

## Database Contract

Migrations define local SQLite equivalents for the production tables:

- `stocks`, `live_quotes`, `intraday_candles`, `daily_candles`
- `financial_metrics`, `technical_indicators`
- `scan_runs`, `scanner_results`, `scanner_snapshots`, `opportunity_rankings`
- `ai_insights`, `ai_insight_snapshots`
- `ml_prediction_snapshots`, `meta_score_snapshots`, `meta_scan_results`
- `trade_plans`, `watchlists`, `alerts`, `portfolio_holdings`
- `backtests`, `backtest_results`, `user_settings`, `audit_logs`

## Page Responsibilities

- Dashboard: market status, KPIs, live monitor, trade availability, opportunities, watchlist, news, and Groww output.
- Intraday: quick signal for one symbol, custom intraday scan, pinned monitor, Telegram alert toggle, Groww feed integration.
- Premarket: premarket scan configuration and latest recommendations.
- Open Confirmation: latest 9:08/open validation shortlist with export.
- Swing: custom swing scan, pinned swing watch, Telegram alert toggle.
- Groww Source: third-party source fetch, symbol resolution, scheduled analysis, push to dashboard/intraday.
- Intelligence Center: combined Final Decision, Meta Scanner, ML Predictions, and AI Insights.
- Watchlist: editable symbol list, order persistence, scan-derived watch rows.
- Reports: backend scan/report archive, Excel download, JSON view.
- Notifications: toast/desktop history and deduplicated backend/Telegram error visibility.
- Settings: persisted scan, model, notification, provider, API, and theme controls.

## Reliability Rules

- Page controls must either perform a real action or stay hidden.
- Heavy scans should run in background tasks, not during page rendering.
- API failures should return explicit loading/error/stale states rather than fallback numbers.
- Telegram failures must be visible in notifications and should not spam repeated toasts.
- SQLite is acceptable for local use, but PostgreSQL plus Redis is the production target.

## Remaining Production Gaps

- Redis sorted-set rankings are not yet active; local implementation uses SQLite plus polling.
- PostgreSQL migration/runtime is not yet wired.
- WebSocket/SSE streaming is not yet active; frontend uses polling fallback.
- True broker-grade live feeds require provider credentials and adapter implementations.
- Some validation metrics depend on generated scan history and will remain empty until scans produce those records.
- End-to-end automated tests still need to be added for scanner rules, APIs, UI rendering, freshness, and alerts.
