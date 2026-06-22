# End-to-End Project Report

Generated on: 2026-06-19  
Project path: `C:\Users\rajmo\OneDrive\Desktop(1)\scanner_project`

## 1. Executive Summary

This project is an NSE-focused stock intelligence platform with two generations of UI:

- A legacy Python/aiohttp web UI served from `ui/app.py` and `ui/static`.
- A newer premium Next.js V20 frontend in `frontend/`, backed by the same Python API.

The product goal is to help a user find, analyze, filter, monitor, and report profitable stock opportunities across premarket, open-confirmation, intraday, swing, Groww-sourced, watchlist, AI/ML/meta, and final-decision workflows.

The codebase has meaningful scanner, analysis, scoring, reporting, alerting, and UI functionality. It is not yet a fully production-grade real-time trading intelligence system because runtime state is still split across JSON files, SQLite, localStorage, polling, and generated reports. PostgreSQL, Redis, a backend WebSocket service, broker-grade tick feeds, authentication, and durable background workers are not yet active.

Overall current status:

- Backend API: Broad and functional, with 151 aiohttp routes registered.
- Frontend build: TypeScript validation passes.
- Python syntax: 85 source files parse successfully.
- Unit tests: 9 tests pass through the project virtualenv.
- Database: SQLite schema is present with 46 tables.
- Live provider: Adapter layer exists, but only the Yahoo Finance provider is implemented.
- Real-time: One-second polling is implemented in many frontend pages. Backend WebSocket/Redis streaming is scaffold-level only.
- Reports: Excel generation is real and tested, but scan-type classification can still mix intraday, swing, and watchlist rows if metadata is incomplete.
- Security: `.env.example` contains real-looking Telegram bot credentials and should be sanitized immediately.

## 2. Project Structure

Important source folders:

- `analysis/`: Technical, fundamental, trend, momentum, liquidity, delivery, event, options, and market-open analysis modules.
- `backtesting/`: Backtest, optimization, walk-forward, strategy testing, and performance metrics.
- `data/`: Market data, direct feeds, yfinance utilities, provider abstraction, news, options, sector, universe, macro, and cache logic.
- `frontend/`: Next.js 14 frontend with dashboard, scanner, watchlist, reports, settings, and intelligence pages.
- `migrations/`: SQLite schema migrations for V20, scanner pipeline, meta/final decision, realtime snapshots, and enterprise contract tables.
- `ml/`: Feature engineering, model training, prediction, and probability ranking.
- `regime/`: Trend and volatility regime detectors.
- `reports/`: Excel export and report generation.
- `scanners/`: Scanner router, premarket-to-open-confirmation pipeline, meta scanner, and final decision engine.
- `scoring/`: Score engine, ranking engine, quality filters, confidence model, premarket gate, and risk model.
- `sentiment/`: News, geopolitical, FII/DII, and global sentiment logic.
- `trading/`: Signal, target, and trade engines.
- `ui/`: Python aiohttp backend, SQLite V20 store, JSON scan storage, AI intelligence layer, legacy static UI.
- `utils/`: Logging, helper functions, and Telegram delivery.
- `tests/`: Focused tests for scoring, quality filters, reports, market-open validation, and UI storage.

Generated or runtime-heavy folders:

- `.scanner_cache/`: Very large feed/cache folder.
- `tmp_pytest/`, `pytest-cache-files-*`, `.pytest_tmp/`: Test/cache leftovers.
- `reports/output/`: Generated Excel files.
- `ui/data/*.json`: Saved scan outputs.
- `ui/data/v20.sqlite`: Local SQLite database.
- `logs/`: Runtime logs.
- `frontend/node_modules/` and `frontend/.next/`: Frontend dependency/build folders.

## 3. Runtime Entry Points

Backend:

```powershell
python -m ui.app
```

Default backend port:

```text
5000
```

Frontend:

```powershell
cd frontend
npm.cmd run dev
```

Default frontend URL:

```text
http://127.0.0.1:3000/dashboard
```

Frontend API routing:

- `frontend/next.config.js` rewrites `/api/:path*` to `BACKEND_URL` or `http://127.0.0.1:5000`.
- `frontend/src/lib/api.ts` also supports selecting API target mode in localStorage.

## 4. Backend API Surface

The backend is in `ui/app.py` and registers 151 routes. Major API groups:

Core:

- `GET /api/health`
- `GET /api/market/widgets`
- `GET /api/dashboard/live`
- `GET /api/realtime/snapshot`

Classic scan lifecycle:

- `POST /api/scan`
- `POST /api/scan/start`
- `POST /api/scan/stop`
- `POST /api/scan/stop-all`
- `POST /api/scan/pause`
- `POST /api/scan/resume`
- `GET /api/scan/active`
- `GET /api/scan/active/all`
- `GET /api/scan/{scan_id}/status`
- `GET /api/scans`
- `GET /api/scans/{scan_id}`

Dedicated scanner APIs:

- `POST /api/scans/{family}/run`
- `GET /api/scans/{family}/latest`
- `GET /api/scans/{family}/{scan_id}/results`
- `GET /api/scanners/{scan_type}/latest`

Pipeline APIs:

- `GET /api/scans/pipeline/today`
- `POST /api/scans/pipeline/prepare`

Meta, ML, and final decision:

- `POST /api/meta-scanner/run`
- `GET /api/meta-scanner/latest`
- `GET /api/meta-scanner/{timeframe}`
- `GET /api/meta-scanner/{symbol}/details`
- `GET /api/meta-scanner/conflicts`
- `GET /api/meta-scanner/agreements`
- `GET /api/final-decisions/latest`
- `GET /api/ml/predictions`
- `GET /api/ml/predictions/{symbol}`

Stock intelligence:

- `GET /api/stocks/{symbol}/analysis`
- `GET /api/stocks/{symbol}/trade-plan`
- `GET /api/ai/insights/{symbol}`
- `GET /api/ai/market-summary`
- `GET /api/ai/stock/{symbol}/insight`
- `GET /api/ai/stock/{symbol}/trade-plan`
- `GET /api/ai/scanner/{scan_type}/insights`
- `GET /api/ai/watchlist/insights`
- `GET /api/ai/portfolio/insights`
- `GET /api/ai/reports/daily`
- `POST /api/ai/copilot/query`
- `POST /api/ai/insights/refresh`
- `POST /api/ai/alerts/create`

V20 data APIs:

- `GET /api/v20/dashboard`
- `GET /api/v20/stocks`
- `GET /api/v20/indices`
- `GET /api/v20/news`
- `GET /api/v20/quote/{symbol}`
- `GET /api/v20/candles/{symbol}`
- `GET /api/v20/watchlist`
- `POST /api/v20/watchlist`
- `GET /api/v20/alerts`
- `POST /api/v20/alerts`
- `GET /api/v20/portfolio`
- `GET /api/v20/reports`
- `GET /api/v20/backtests`
- `POST /api/v20/backtests`
- `GET /api/v20/paper-trades`
- `POST /api/v20/paper-trades`
- `GET /api/v20/settings`
- `POST /api/v20/settings`
- `GET /api/v20/saved-scanners`
- `POST /api/v20/saved-scanners`
- `GET /api/v20/saved-filters`
- `POST /api/v20/saved-filters`

Reports and exports:

- `GET /api/reports/{scan_id}/excel`
- `GET /api/export/watchlist`
- `GET /api/history`

Settings and saved strategy APIs:

- `GET /api/settings`
- `POST /api/settings`
- `GET /api/watchlist/order`
- `POST /api/watchlist/order`
- `GET /api/strategies`
- `GET /api/strategies/{strategy_id}`
- `POST /api/strategies`
- `DELETE /api/strategies/{strategy_id}`

Telegram:

- `POST /api/telegram/stock-alert`
- `GET /api/telegram/status`
- `POST /api/telegram/test`

Groww:

- `GET /api/sources/groww/intraday`

## 5. Backend Architecture

### 5.1 Main Scanner Pipeline

Primary scan orchestration is in `main.py`.

Important responsibilities:

- Load symbol universe.
- Fetch OHLCV data.
- Fetch benchmark and sector data.
- Build breadth payload.
- Perform fast candidate scoring.
- Sort and shortlist candidates.
- Fetch global market data.
- Perform deep analysis.
- Optionally perform market-open validation.
- Optionally perform walk-forward validation.
- Rank final results.
- Build fallback tiered report rows if strict final ranking is empty.
- Generate Excel report.
- Optionally dispatch Telegram scan summary/report.

The pipeline generates these result groups:

- `results`: analyzed candidate rows.
- `filtered_150`: broad filtered/analyzed rows.
- `top_25`: intermediate shortlist.
- `final_top_10`: display shortlist, falling back to top rows when strict ranked output is empty.
- `ranked`: strict quality-ranked output, often empty in saved scans.

Important finding:

Current saved scans show that analysis does happen even when `ranked` is empty. Consumers must not equate empty `ranked` with empty analysis. Several saved scans have full `results`, `filtered_150`, `top_25`, and `final_top_10`, while `ranked` is zero because strict quality filters removed final candidates.

### 5.2 Scan-Type Routing

`scanners/router.py` defines scanner profiles:

- Premarket Scanner
- 9:08 Open Confirmation Scanner
- Intraday Elite Scanner
- Swing Scanner
- Watchlist Scanner
- Standard Scanner

Each profile has a mode, family, bucket, stage, display name, default top-N, candidate pool, validation pool, and allowed sources.

Current issue:

Older saved scan JSON files often have `scan_family`, `scanner_bucket`, and `pipeline_stage` as `None`. This weak metadata is one reason report sheets and frontend pages can mix or misclassify intraday/swing/watchlist rows.

### 5.3 Premarket to Open Confirmation to Intraday Pipeline

`scanners/premarket_pipeline.py` provides:

- `build_open_confirmation_payload()`
- `build_intraday_payload()`
- `pipeline_snapshot()`

Expected flow:

1. Premarket scan creates candidate list.
2. Open-confirmation stage takes up to 25 premarket candidates and checks 9:08 data.
3. Intraday stage takes up to 10 open-confirmed candidates and runs 5m intraday analysis.

Current status:

- The payload builders exist.
- API routes exist.
- Data still depends on saved scan payloads and yfinance availability.
- No durable background scheduler/job runner is enforcing the full pipeline automatically in production style.

### 5.4 Meta Scanner

`scanners/meta_scanner.py` builds meta decisions by reading recent saved scan JSON through `ui.storage.list_scans()` and `load_scan()`.

It groups rows by symbol, computes:

- scan types matched
- scanner agreement score
- signal strength
- AI confidence
- ML confidence
- risk score
- backtest score
- risk-adjusted score
- meta score
- conflict warnings
- trade plan

Then it passes rows into the final decision engine.

Current status:

- Functional and connected to APIs/frontend.
- Uses saved JSON scans as source of truth, not a normalized database/event stream.
- This means old scans with weak metadata can reduce meta accuracy.

### 5.5 Final Decision Engine

`scanners/final_decision.py` answers:

- show to user
- trade
- watch
- reject

Strict trade rules:

- meta score >= 80
- risk score <= 55
- backtest score >= 70
- ML confidence >= 65
- risk reward >= 2
- no avoid/reject source action
- no conflicts

Design is conservative: no trade is preferred over bad trade.

Current status:

- Implemented and backend-wired.
- Frontend combines final decisions into `/ai-insights`.
- Trade candidates may be scarce because rules are intentionally strict.

### 5.6 AI Intelligence

`ui/ai_intelligence.py` provides:

- market summary
- stock insight
- trade plan
- scanner insights
- watchlist insights
- portfolio insights
- daily report
- copilot query
- alert creation

It uses V20 store rows and persisted scan/scoring fields.

Current issue:

- This is deterministic scoring/explanation logic, not an external LLM or trained AI service.
- It can generate insights only from data present in SQLite and saved scans.
- If V20 store has only a small live universe, insights become narrow.

### 5.7 ML Layer

`ml/` contains:

- feature engineering
- model trainer
- predictor
- probability ranker

Current issue:

- ML output appears to be lightweight/static unless trained historical trade outcomes are added.
- The frontend and API expose ML predictions, but deeper production ML lifecycle is not complete.

### 5.8 Market Data Provider

`data/market_data_provider.py` defines a provider adapter interface:

- `get_indices()`
- `get_quote()`
- `get_historical_prices()`
- `get_intraday_prices()`
- `get_financial_metrics()`
- `get_news()`

Implemented provider:

- Yahoo Finance provider.

Missing production adapters:

- Upstox
- Zerodha Kite
- Angel One SmartAPI
- FYERS
- Dhan
- Alpha Vantage
- Finnhub
- Twelve Data
- Polygon
- Paid NSE/BSE-compatible tick provider

Important finding:

Provider abstraction exists, but provider switching is not truly implemented. If `MARKET_DATA_PROVIDER` is anything other than `yfinance`, the app logs a warning and falls back to yfinance.

### 5.9 News and Direct Feeds

News sources:

- NewsAPI if `NEWS_API_KEY` is configured.
- Google News RSS fallback.
- NSE corporate announcements where available.
- Direct NSE feeds for some event data.

Current status:

- Market and stock news fetching exists.
- Optional direct feed failures are downgraded for many HTTP statuses.
- NSE/Groww web feeds can still fail due provider changes, SSL issues, bot protection, or rate limiting.

### 5.10 Telegram Alerts

`utils/telegram.py` supports category-specific Telegram configuration:

- Intraday
- Swing
- Premarket
- Others

Backend APIs:

- status check
- test message
- stock alert message

Frontend integrations:

- Dashboard live monitor target/stop alerts.
- Intraday selected monitor alerts.
- Swing selected monitor alerts.
- Scan center scan-complete notification flags.

Current risks:

- Telegram depends entirely on environment variables.
- `.env.example` contains real-looking bot tokens/chat IDs and must be sanitized.
- The app should surface exact missing/invalid token/chat causes in UI, not only a generic failure.
- Telegram network calls are synchronous `requests` calls and can block if Telegram/API is slow.

## 6. Data Storage and Database

### 6.1 Current Storage Layers

The app currently uses several storage mechanisms:

- SQLite: `ui/data/v20.sqlite`
- JSON scan files: `ui/data/202*.json`
- Settings JSON: `ui/data/settings.json`
- Strategy JSON files: `ui/data/strategies/*.json`
- Browser localStorage: live monitor, Groww results/settings, desktop alert preference, custom scan symbols, optimistic scan state
- Excel output: `reports/output/*.xlsx`
- Cache pickles: `.scanner_cache/**`

This split works locally but is not ideal for production. A production design should centralize durable entities in PostgreSQL and volatile live state in Redis or a broker/event stream.

### 6.2 SQLite Schema

Current SQLite table count from audit: 46.

Observed row counts:

- `stocks`: 1
- `stock_prices`: 4
- `market_indices`: 2
- `financial_metrics`: 1
- `profitability_scores`: 1
- `ai_insights`: 92
- `watchlist_items`: 2
- `alerts`: 6
- `news_articles`: 17
- `reports`: 0
- `backtests`: 0
- `paper_trades`: 1
- `scan_runs`: 0
- `premarket_scan_results`: 0
- `open_confirmation_results`: 0
- `intraday_scan_results`: 0
- `meta_scan_results`: 241
- `live_quotes`: 3
- `scanner_snapshots`: 0
- `opportunity_rankings`: 0
- `trade_plans`: 0
- `audit_logs`: 0

Interpretation:

- The schema exists.
- Current V20 database content is thin.
- Saved scan JSON files contain richer scan history than normalized DB tables.
- `scan_runs` and scan-result tables are empty even though JSON scan outputs exist.
- Dashboard quality depends heavily on latest ingestion into V20 tables.

### 6.3 Migrations

Migrations present:

- `001_v20_schema.sql`: Users, stocks, prices, metrics, scores, AI, watchlists, portfolio, alerts, news, reports, backtests, paper trades, settings, saved scanners/filters.
- `002_scanner_pipeline.sql`: scan runs and scan-stage result tables.
- `003_meta_final_decision.sql`: meta scan and scanner agreement/conflict tables.
- `004_realtime_snapshots.sql`: live quotes, intraday candles, scanner snapshots, opportunity rankings, AI/ML/meta snapshots.
- `005_enterprise_realtime_contract.sql`: daily candles, technical indicators, generic scanner results, trade plans, backtest results, audit logs.

Current migration handling:

- `ui/v20_store.py` creates core schema automatically.
- Optional enterprise migrations are guarded so backend startup does not fail if SQLite/OneDrive produces transient disk I/O errors.

### 6.4 Database Risks

- SQLite is inside OneDrive and sometimes appears as a reparse point. This can cause locking, access denied, or disk I/O errors.
- `ui/data/v20.sqlite-journal` is visible and not currently ignored by `.gitignore`.
- Some tests and smoke checks created temporary cache DB files that Windows/OneDrive can lock.
- Production should move DB storage outside OneDrive and use PostgreSQL.

## 7. Frontend Architecture

Frontend stack:

- Next.js 14.2.5
- React 18.3.1
- TypeScript
- Redux Toolkit
- React Redux
- Axios
- SWR dependency present
- Lucide icons

State:

- Redux slices for dashboard, scan, watchlist, settings.
- Local component state for filters/forms.
- localStorage for live monitor rows, custom symbols, Groww automation settings/results, desktop alerts, notifications, optimistic active scans.

Realtime behavior:

- Most key pages poll every 1 second.
- A WebSocket hook exists, but no backend WebSocket server route was found in `ui/app.py`.
- Realtime snapshot API reports `stream: polling`, `websocket: false`, `redis: false`.

Frontend API adapter:

- `frontend/src/lib/api.ts` centralizes backend calls.
- Includes active scan optimistic state to reduce perceived scan-status lag.
- Includes canonical helpers for live dashboard, scanner latest, stock analysis, trade plan, and ML prediction.

## 8. Page-by-Page Report

### 8.1 Dashboard - `/dashboard`

Purpose:

- Main command center for live indices, KPIs, live stock monitor, top profitable stocks, sector/risk/breadth analytics, AI insights, quick actions, opportunities, watchlist, and news.

Backend/data:

- `GET /api/v20/dashboard`
- `GET /api/scan/active/all`
- `GET /api/v20/quote/{symbol}`
- `POST /api/v20/watchlist`
- `POST /api/v20/alerts`
- `POST /api/v20/paper-trades`
- `POST /api/telegram/stock-alert`

Implemented:

- One-second dashboard refresh.
- One-second visible quote refresh.
- Live stock monitor persisted in localStorage.
- Symbol normalization to uppercase `.NS`.
- Target/stop status calculation.
- Telegram alert attempt on near/hit target/stop.
- Add to watchlist, create alert, paper trade, save filter.

Risks:

- Dashboard V20 database currently has only one stock row, so the dashboard can look sparse.
- Top opportunities depend on V20 store ingestion, not directly on full latest JSON scan payload.
- One-second polling can overload yfinance or backend if many rows are visible.
- Telegram failures can repeat unless deduping is carefully tuned.

### 8.2 Premarket Scanner - `/premarket`

Purpose:

- Premarket opportunity scanner and source for open-confirmation pipeline.

Backend/data:

- `GET /api/scans`
- `GET /api/scans/{scan_id}`
- `POST /api/scan/start`
- `GET /api/scan/{scan_id}/status`
- `GET /api/v20/quote/{symbol}`
- `GET /api/scan/active/all`

Implemented:

- Loads latest scan payload.
- Runs scans.
- Polls active scan status.
- Refreshes visible quotes.
- Filters/searches rows.
- Shows backend loading/error states.

Risks:

- Uses `getLatestScanWithResults()` with broad scan selection. It can accidentally show a non-premarket scan if metadata is weak.
- Strong separation requires saved scan metadata to include `scan_family=premarket`.

### 8.3 Open Confirmation - `/open-confirmation`

Purpose:

- Validate premarket candidates around 9:08/open using live/intraday data.

Backend/data:

- `GET /api/scans/open-confirmation/latest`
- `POST /api/scans/open-confirmation/run`

Implemented:

- Run open-confirmation scan.
- Auto-refresh toggle.
- Export CSV.
- Displays validation fields such as open price, target-time price, gap hold, VWAP status, volume, score, action, reason.

Risks:

- Depends on premarket scan availability.
- Uses yfinance intraday data; true 9:08 tick/quote precision is not guaranteed.

### 8.4 Stock Scanner / Scan Center - `/scan-center`

Purpose:

- Central launcher for premarket, intraday, swing, watchlist, sector, industry, full NSE, and custom scans.

Backend/data:

- `POST /api/scan/start`
- `GET /api/scans`
- `GET /api/scan/active/all`
- `GET /api/scan/{scan_id}/status`
- `POST /api/scan/stop`
- `POST /api/scan/stop-all`
- `POST /api/scan/pause`
- `POST /api/scan/resume`

Implemented:

- Scan type presets.
- Custom stocks input with `.NS` normalization.
- Start, stop selected, stop all, pause, resume.
- Telegram checkbox.
- Active scan table.
- Backend status polling every second.

Risks:

- Multiple concurrent scans can stress local CPU/network/yfinance.
- Pause/resume is status-level; scanner worker internals may not truly pause mid-analysis unless the task checks pause state.
- Backend scan status is in-memory, so active task state is lost on backend restart.

### 8.5 Groww Source - `/groww-intraday`

Purpose:

- Fetch stocks from `https://groww.in/stocks/intraday`, resolve symbols, run intraday scan, push filtered rows to dashboard monitor and intraday page.

Backend/data:

- `GET /api/sources/groww/intraday`
- `POST /api/scan/start`
- `GET /api/scan/{scan_id}/status`

Implemented:

- Fetch Groww source.
- Run Groww intraday analysis.
- Save results in localStorage.
- Push symbols to intraday custom symbols.
- Add filtered rows to dashboard live monitor.
- Auto-check settings UI.

Risks:

- Automation is frontend/localStorage driven, not a durable backend scheduled job.
- Groww scraping can break due SSL, HTML changes, or anti-bot controls.
- Results are not normalized into a dedicated Groww database table.

### 8.6 Watchlist - `/watchlist`

Purpose:

- Manage pinned stocks and watchlist analytics.

Backend/data:

- V20 stock/watchlist/alert APIs.
- Frontend watchlist state.

Implemented:

- Backend-wired watchlist display/actions.
- Alert-related metrics.
- Add/remove style flows are present through API helper layer.

Risks:

- Watchlist depends on V20 store stocks. If V20 store has only one active stock, watchlist actions are constrained.
- Needs clearer reconciliation between dashboard live monitor, V20 watchlist table, and frontend state.

### 8.7 Intraday Scanner - `/intraday`

Purpose:

- Fast intraday analysis, custom symbol scan, quick signal generation, selected monitor alerts.

Backend/data:

- `GET /api/intraday/quick-signal/{symbol}`
- `POST /api/scan/start`
- `GET /api/scans`
- `GET /api/scans/{scan_id}`
- `GET /api/v20/quote/{symbol}`
- `POST /api/telegram/stock-alert`

Implemented:

- Custom symbols persisted with `custom-intraday-symbols`.
- Uppercase `.NS` normalization.
- Quick signal for individual symbols.
- Start custom intraday scan.
- One-second latest scan/active scan/quote refresh.
- Telegram alerts for selected monitor rows.

Risks:

- The page loads latest results using scan-mode regex and horizon filters. Weak scan metadata can mix premarket, Groww, and intraday rows.
- One-stock intraday scan can still be slow because full `main.py` deep-analysis path performs many modules, backtest/optimization hooks, and market data calls.
- For instant one-stock signals, the quick signal route is the better path than full scan.

### 8.8 Swing Scanner - `/swing`

Purpose:

- Multi-day swing analysis and custom swing scans.

Backend/data:

- `POST /api/scan/start`
- saved scan APIs
- quote APIs
- Telegram stock-alert API

Implemented:

- Custom symbols persisted with `custom-swing-symbols`.
- Uppercase `.NS` normalization.
- Custom swing scan with candidate/validation pool controls.
- Telegram alerts for selected monitor rows.

Risks:

- Same metadata risk as intraday: saved scans must clearly mark `scan_family=swing`.
- Current report category logic can still reclassify rows if metadata is missing.

### 8.9 Intelligence Center - `/ai-insights`

Purpose:

- Combined AI Insights, Meta Scanner, ML Predictions, and Final Decision Center.

Backend/data:

- `GET /api/final-decisions/latest`
- `GET /api/meta-scanner/latest`
- `GET /api/ml/predictions`
- `GET /api/ai/scanner/{scan_type}/insights`
- `GET /api/ai/market-summary`
- `POST /api/meta-scanner/run`
- `GET /api/v20/dashboard`

Implemented:

- Combined workspace as requested.
- Tabs for final decision, meta scanner, ML predictions, and AI insights.
- Run meta scanner action.
- Show rejected toggle.
- Backend loading and empty states.

Risks:

- Final decision/meta data is derived from saved scan JSON and current V20 rows.
- ML predictions are confidence-style outputs, not a fully trained production model workflow.
- If scan metadata is weak or no recent scans exist, this page correctly shows empty/no forced trade states.

### 8.10 Reports - `/reports`

Purpose:

- View backend-generated scan reports and open Excel/JSON scan outputs.

Backend/data:

- `GET /api/scans`
- `GET /api/scans/{scan_id}`
- `GET /api/reports/{scan_id}/excel`

Implemented:

- Loads recent scan details.
- Displays report metrics.
- Opens Excel export.
- Opens raw scan JSON.
- Shows only backend-generated reports.

Risks:

- Some latest JSON scans refer to report paths that may not exist in `reports/output` if old artifacts were removed or ignored.
- Excel sheet classification can mix scan types if scan metadata is missing.
- Generated report files are ignored by git and should not be treated as source.

### 8.11 Notifications - `/notifications`

Purpose:

- Review frontend notification history and control desktop alerts.

Backend/data:

- Browser localStorage notification history.
- Browser Notification API.

Implemented:

- Desktop alerts toggle.
- Notification history.
- Clear history action.
- Deduped toast persistence.

Risks:

- Notification history is local to browser, not persisted in backend `audit_logs` or a notification table.
- Backend scan/Telegram events are not centrally written to notification history unless surfaced through frontend toasts.

### 8.12 Settings - `/settings`

Purpose:

- Configure scan thresholds, modules, API/feed behavior, notifications, risk, and themes.

Backend/data:

- `GET /api/settings`
- `POST /api/settings`
- Redux settings slice
- localStorage desktop alert setting

Implemented:

- Category-based settings UI.
- Save configuration.
- Import/export JSON.
- Reset defaults.
- Rollback to last saved.
- Theme/density settings.
- Desktop alert sync.

Risks:

- Some settings are stored but not guaranteed to affect every scanner module unless explicitly read by the scan payload or backend.
- There are two settings systems: `ui/data/settings.json` and V20 `user_settings`.
- Configuration should be normalized into one backend schema.

## 9. Reporting System

Report generation:

- `reports/report_generator.py`
- `reports/excel_export.py`

Excel sheets include:

- `All_Stocks_Live_Data`
- `Filtered_150`
- `Top_25`
- `Final_Top_10`
- clear trade sheets such as intraday and swing outputs
- market-open validation rows when available

Strengths:

- Report generator has extensive field mapping.
- Tests verify report generation and tiered sheets.
- Scan outputs include report paths.

Important issue:

Saved scan sample `20260617_110456.json` had:

- `results`: 97
- `filtered_150`: 97
- `top_25`: 25
- `final_top_10`: 10
- `ranked`: 0
- summary intraday_ready: 6
- summary swing_ready: 8

This means analysis happened, but strict ranking produced no `ranked` rows. Reports and pages should explicitly use the right row group per scan type:

- Intraday page/report: intraday-specific rows from current scan mode or rows with `best_horizon=Intraday`.
- Swing page/report: swing-specific rows from current scan mode or rows with swing horizon.
- Final top report: only final decision rows, not mixed watchlist/intraday/swing rows unless intentionally labeled.

## 10. Quality Filters and Ranking

`scoring/quality_filter.py`:

- Fast filter rules for coarse quality/confidence/risk/volume.
- Deep filter rules for score, confidence, ML, quality, profitability, expected return, premarket grade, risk reward, stop distance, data reliability, drawdown, risk level, and status.
- Strict deep filter requires `min_expected_return_pct=5`.

`scoring/ranking_engine.py`:

- Filters rows according to score, confidence, profitability, ML, backtest/profit factor, premarket grade, risk reward, stop distance, data reliability, expected return, risk level, and status.
- Strict mode is intentionally much tighter.
- Ranking score combines absolute score, confidence, ML, premarket grade, profitability, expected return, quality, data reliability, profit factor, backtest win rate, and walk-forward metrics.

Important finding:

The "Deep quality filter removed all final candidates" message can be correct if rows fail strict conditions. The app now falls back for tiered report sheets, but final trade ranking remains conservative.

Recommended improvement:

Store every rejected row with `rejection_reasons` in normalized DB tables and show those reasons clearly on each scanner page. This will explain why `ranked=0` while `filtered_150` has rows.

## 11. Real-Time Behavior

Current realtime implementation:

- Dashboard polls every 1 second.
- Intraday and swing pages poll latest scan, active scans, and visible quotes every 1 second.
- Top market bar polls realtime snapshot/indices every 1 second.
- Scan center polls active scans every 1 second.
- Global header polls active scan status every 1 second.
- Open confirmation polls every 3 seconds when auto-refresh is enabled.

Backend realtime:

- `GET /api/realtime/snapshot`
- SQLite tables for live quotes, scanner snapshots, opportunity rankings, AI/ML/meta snapshots.
- Realtime payload explicitly reports `stream=polling`, `websocket=false`, `redis=false`, `hot_cache=sqlite+memory`.

Important limitation:

This is near-real-time polling, not true streaming. One-second UI refresh does not guarantee one-second market data freshness because upstream yfinance/provider data may update slower.

## 12. Security Review

Critical:

- `.env.example` contains real-looking Telegram bot tokens and chat IDs.
- These credentials should be treated as compromised.
- Rotate/delete the bot tokens in Telegram BotFather.
- Replace values in `.env.example` with empty placeholders.
- Keep real `.env` local only and never commit it.

Other security gaps:

- No authentication/session enforcement is active.
- Default local user is seeded.
- CORS is permissive in local backend middleware.
- Telegram errors can expose provider response snippets in logs.
- SQLite local file is not encrypted.

## 13. Performance Review

Strengths:

- Bulk market data fetching exists.
- Cache layer exists for OHLCV, quotes, events, fundamentals, universe, options.
- Frontend uses polling and normalizers.
- Scan center supports worker count.

Risks:

- One-second polling across many pages can cause backend and provider load.
- yfinance is not designed for high-frequency tick updates.
- Full intraday scan for one stock can still run the heavy scan pipeline.
- `.scanner_cache` has thousands of files and can become slow under OneDrive.
- Frontend `frontend/` contains `node_modules` and build artifacts, making local file scans heavy.

Recommended:

- For one-stock instant analysis, route the UI to `/api/intraday/quick-signal/{symbol}` instead of full `main.py` scan.
- Use Redis or in-memory process cache for hot quote snapshots.
- Use a proper broker/feed WebSocket for tick updates.
- Debounce or pause polling while forms are focused.
- Keep cache/runtime folders outside OneDrive.

## 14. Verification Results

Commands run during audit:

```powershell
npx.cmd tsc --noEmit
```

Result:

- Passed.

```powershell
python AST parse over main.py and Python source folders
```

Result:

- 85 Python files parsed successfully.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Result:

- 9 passed.
- 1 warning: pytest cache could not create cache path due Windows/OneDrive access denied.

```powershell
ui.v20_store.ensure_db()
```

Result:

- Passed after optional migration guard.
- Core schema ready.
- Enterprise tables present.

## 15. Current High-Priority Issues

### P0 - Exposed Telegram Secrets

`.env.example` contains real-looking Telegram bot tokens/chat IDs. Rotate immediately and replace with blank placeholders.

### P0 - Runtime State Is Split

Important data is spread across SQLite, JSON scan files, reports, and browser localStorage. This causes pages to disagree.

Fix:

- PostgreSQL as source of truth.
- Redis for live state.
- JSON scan files only as export/archive, not primary runtime data.

### P1 - Scan Metadata Is Weak in Existing Outputs

Many saved scans have `scan_family=None` and `pipeline_stage=None`. This breaks strict scan separation.

Fix:

- Always persist `scan_mode`, `scan_family`, `scanner_bucket`, `pipeline_stage`.
- Backfill older JSON or ignore older weak-metadata scans in page selection.

### P1 - Strict Ranking Often Returns Zero

`ranked=0` happens even when analysis rows exist. This is caused by strict deep filters and final ranking gates.

Fix:

- Show rejection reasons per row.
- Separate "analyzed rows", "watch rows", "trade-ready rows", and "hidden/rejected rows".
- Do not label analyzed but rejected rows as missing data.

### P1 - V20 DB Is Thin Compared With Saved Scans

Current SQLite has only one `stocks` row, while saved JSON contains broader scans.

Fix:

- Ingest saved scan rows into normalized scanner tables.
- Populate `scanner_snapshots`, `opportunity_rankings`, `scan_runs`, and scan-stage result tables consistently.

### P1 - One-Second Polling Is Not True Streaming

UI refreshes quickly, but provider data may not change each second.

Fix:

- Use broker/feed WebSocket for quotes.
- Backend WebSocket/SSE channel for frontend.
- Redis pub/sub for scanner status and quote ticks.

### P1 - Reports Can Mix Scan Types

Report category derivation can mix rows when scan metadata is missing.

Fix:

- Generate report sheets based on scan family first.
- Use horizon fallback only when scan family is absent.
- Preserve rejected/analyzed/watch/trade rows in separate sheets.

### P2 - OneDrive SQLite Locking

SQLite under OneDrive can lock or produce disk I/O/access errors.

Fix:

- Move DB/cache/report output outside OneDrive.
- Use local app data path or PostgreSQL.

### P2 - WebSocket Hook Exists Without Backend Stream

Frontend has `useRealtime`, but backend WebSocket is not implemented.

Fix:

- Add `/ws` or SSE endpoint.
- Publish scan status, quote ticks, alert events, and final decision updates.

## 16. Recommended Roadmap

### Phase 1 - Stabilize Current Local Product

1. Sanitize `.env.example` and rotate Telegram tokens.
2. Move SQLite/cache/runtime outputs outside OneDrive.
3. Backfill scan metadata for saved JSON or filter out weak-metadata scans.
4. Ensure every scan start persists `scan_runs` and scanner result rows.
5. Show rejection reasons in every scanner table.
6. Fix report sheet ownership by scan family.
7. Add a "quick one-stock intraday analysis" path on Intraday page that avoids full scan pipeline.

### Phase 2 - Strong Scanner Separation

1. Create dedicated result tables/services for:
   - premarket
   - open confirmation
   - intraday
   - swing
   - Groww intraday
   - watchlist
2. Each page reads only its own table/API by default.
3. Meta scanner reads normalized scanner result tables, not raw JSON files.
4. Final decision engine stores shown/watch/rejected decisions with reasons.

### Phase 3 - True Realtime Platform

1. Add PostgreSQL.
2. Add Redis.
3. Add backend WebSocket/SSE.
4. Add provider-specific live market adapters.
5. Add scheduled workers for Groww source, premarket, open confirmation, intraday refresh, alerts, reports, and news ingestion.
6. Move Telegram and desktop notification events into durable notification/audit tables.

### Phase 4 - Production Hardening

1. Add authentication.
2. Add role/user-specific watchlists, alerts, portfolios, and settings.
3. Add API validation schemas.
4. Add structured logging and audit trails.
5. Add integration tests for each scanner API.
6. Add frontend route smoke tests.
7. Add deployment docs for local and remote server mode.

## 17. Final Assessment

This project is much more than a simple scanner. It already has a strong skeleton for a full stock intelligence platform:

- broad analysis modules
- real scanner pipeline
- quality filters
- scoring and ranking
- reports
- Telegram alerts
- V20 UI
- AI/ML/meta/final-decision layers
- Groww source integration
- live monitor
- watchlist and settings

The main weakness is not the absence of features. The main weakness is source-of-truth consistency. The next serious upgrade should focus less on adding new UI and more on making every scanner write normalized, scan-type-owned rows into the database, then making every frontend page read only that canonical data.

Once source-of-truth is fixed, the platform can move from "feature-rich local scanner" to "production-grade real-time stock intelligence system."
