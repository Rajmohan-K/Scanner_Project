# Pre-Market Stock Scanner

This project is a standalone NSE-focused stock scanner for pre-market intraday and swing selection.

## What It Does

- Loads a symbol universe or auto-fetches the NSE pre-open universe.
- Pulls OHLCV, quote, macro, sector, options, and news data.
- Runs multi-factor technical, momentum, liquidity, sentiment, and market-regime analysis.
- Scores every stock, estimates risk, generates trade levels, and ranks the best setups.
- Produces an Excel report with full scan output plus a cleaner shortlist.

## Current Strengths

- Modular architecture across `data`, `analysis`, `sentiment`, `scoring`, `trading`, `ml`, and `reports`.
- Fast first-pass screening followed by deeper validation on shortlisted names.
- Built-in backtest, walk-forward, and optimization hooks for stronger ranking.
- Dedicated pre-market qualification layer to separate qualified intraday, qualified swing, watchlist, and rejected setups.

## Important Limits

- News sentiment is headline-based polarity, not deep event extraction.
- The ML probability model is a lightweight static linear model unless you replace it with a trained model.
- Sector mapping is still incomplete and should be expanded for better sector-relative comparisons.
- Some direct-feed endpoints can change over time; `FII_DII_FEED_URL` is configurable for a more authoritative institutional-flow source.

## Setup

```bash
pip install -r requirements.txt
```

Create a local environment file from `.env.example` and set `NEWS_API_KEY` if you want live news.
For stronger direct institutional-flow ingestion, set `FII_DII_FEED_URL` to your preferred JSON feed.

## Run

Watchlist mode:

```bash
python main.py --top-n 10
```

Full NSE universe mode:

```bash
python main.py --auto-nse-universe --top-n 20 --candidate-pool 200 --validation-pool 40 --strict-shortlist
```

Use a custom symbol file:

```bash
python main.py --symbols-file all_symbols.txt --top-n 15
```

## Run The UI

Launch the premium local web interface:

```bash
python ui/app.py
```

Then open:

```text
http://127.0.0.1:5000
```

### Quick Scan Features

The web interface now includes multiple ways to scan whenever you want:

**Quick Scan Buttons:**
- **⚡ Scan Watchlist**: Instantly scan your 8-stock blue-chip watchlist (RELIANCE, INFY, TCS, etc.)
- **🌐 Scan All NSE**: Scan the entire NSE universe (~2000 stocks) for opportunities
- **🔴 Scan Now**: Execute a scan with your current custom settings

**Stock Selection Modes:**
- **Watchlist Mode**: Pre-configured 8 major NSE stocks
- **All Stocks Mode**: Full NSE market universe discovery

**Live Features:**
- Live progress bar showing scan completion percentage
- Data freshness indicator showing when results were last updated
- Real-time progress updates during scanning
- Live auto-refresh capability before market open (configurable)

UI features:

- Premium control room layout for pre-market scanning
- Custom symbol watchlists or full NSE universe mode
- Summary cards for qualified setups, grade, ML quality, and horizon split
- Ranked setups table with action, grade, confidence, event score, and risk-reward
- Setup detail panel with trade reason, pre-market notes, earnings timing, block-deal activity, and top drivers
- **NEW**: Interactive candlestick mini-charts per stock showing recent price action
- **NEW**: Enhanced comparison analytics showing new entrants, dropped setups, and grade movers
- **NEW**: Live quick-scan buttons for one-click analysis
- **NEW**: Auto-refresh during pre-market window with configurable timing

## Scheduled Scanning

Run automated daily scans at specific times:

```bash
# Run immediately and schedule for 9:00 AM IST daily
python scheduled_scan.py --run-now --schedule-time 09:00

# Just schedule without running now
python scheduled_scan.py --schedule-time 09:00
```

## Desktop Application

Build and run as a standalone Windows executable:

```bash
# Install build dependencies
pip install pyinstaller>=6.0.0

# Build the executable
python build.py

# Run the desktop app
./dist/StockScanner.exe
```

The executable bundles the entire application and opens your default browser to the web interface.

## Output

The scanner prints ranked setups to the terminal and writes an Excel report from `reports/report_generator.py`.

Key output fields:

- `premarket_grade`: overall decision quality before market open
- `premarket_status`: `Qualified`, `Watchlist`, or `Rejected`
- `best_horizon`: `Intraday`, `Swing`, `Watchlist`, or `Rejected`
- `premarket_action`: `BUY`, `SELL`, `WATCH`, or `AVOID`
- `event_score`: direct event impact from earnings timing, block deals, institutional flows, and geopolitical feed pressure

## Best Next Upgrades

1. ✅ **COMPLETED**: Add scheduler for automatic morning runs
2. ✅ **COMPLETED**: Desktop packaging as .exe
3. ✅ **COMPLETED**: Better comparison analytics (new entrants, dropped setups, grade movers)
4. ✅ **COMPLETED**: Candlestick mini-charts per stock
5. Replace heuristic sector mapping with a complete NSE sector map.
6. Add real event ingestion for earnings calendar, results, block deals, and geopolitical feeds.
7. Train the ML layer from actual historical trade outcomes instead of static weights.
