# Version 20 Stock Intelligence Platform

Version 20 adds a premium fintech dashboard backed by SQLite models, a V20 API layer, a live-data provider adapter, a profitability scoring engine, watchlist actions, alerts, reports, backtesting records, paper trades, saved scanners, saved filters, and user settings.

## Run Locally

Backend:

```powershell
python -m ui.app
```

Frontend:

```powershell
cd frontend
npm.cmd run dev
```

Open:

```text
http://127.0.0.1:3000/dashboard
```

## Environment

Frontend reads the backend URL from:

```text
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:5000
```

If omitted, the frontend defaults to `http://127.0.0.1:5000`.

Live market data provider configuration:

```text
MARKET_DATA_PROVIDER=yfinance
MARKET_INDEX_SYMBOLS=^NSEI,^BSESN
```

Broker/vendor keys must be configured through environment variables only. Do not hardcode keys in the app.

## Database

SQLite database:

```text
ui/data/v20.sqlite
```

Migration:

```text
migrations/001_v20_schema.sql
```

The database is created automatically when a V20 API is called. The app does not seed fake stocks, fake prices, fake news, fake watchlist items, or fake dashboard values. If live provider data or live scan results are unavailable, V20 APIs return empty/unavailable states and the frontend displays retry/unavailable UI.

Default seeded user:

```text
analyst@scanner.local
```

Authentication is structured at the model level through `users` and `user_settings`, but local V20 endpoints currently run as the default analyst user.

## Main APIs

```text
GET  /api/v20/dashboard
POST /api/v20/refresh
GET  /api/v20/stocks
GET  /api/v20/indices
GET  /api/v20/news
GET  /api/v20/quote/{symbol}
GET  /api/v20/candles/{symbol}
GET  /api/v20/watchlist
POST /api/v20/watchlist
GET  /api/v20/alerts
POST /api/v20/alerts
GET  /api/v20/portfolio
GET  /api/v20/reports
GET  /api/v20/backtests
POST /api/v20/backtests
GET  /api/v20/paper-trades
POST /api/v20/paper-trades
GET  /api/v20/settings
POST /api/v20/settings
GET  /api/v20/saved-scanners
POST /api/v20/saved-scanners
GET  /api/v20/saved-filters
POST /api/v20/saved-filters
```

## Stock Query Filters

`GET /api/v20/stocks` supports:

```text
search
sector
rating
min_profitability
min_ai_score
max_risk
min_roe
max_pe
sort
direction
limit
offset
```

Sortable columns:

```text
symbol
price
market_cap
profitability_score
ai_score
pe
roe
eps_growth
```

## Scoring Engine

The V20 profitability engine computes:

```text
Profitability Score
Growth Score
Value Score
Momentum Score
Risk Score
Quality Score
Final AI Score
AI Rating
Rating explanation
```

Rating labels:

```text
Strong Buy
Buy
Watch
Hold
Avoid
```

The engine uses available scan/fundamental fields when present and conservative defaults when the live source does not provide a metric.

## Production Notes

For production deployment, connect authenticated users to the V20 endpoints, configure durable market/news/fundamental data feeds, and run the existing scanner jobs on a schedule. The current V20 implementation is fully wired for local use and stores actions in SQLite.
