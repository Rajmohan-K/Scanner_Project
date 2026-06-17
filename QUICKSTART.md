# Quick Start Guide - Live Stock Scanner

## What You Can Do Right Now

### 🚀 **One-Click Scanning**

The simplest way to get started:

```bash
python ui/app.py
```

Then open your browser to `http://127.0.0.1:5000`

### ⚡ **Quick Scan Options**

On the left sidebar, you'll see three quick scan buttons:

**1. ⚡ Scan Watchlist**
- Instantly scans 8 major NSE stocks (RELIANCE, INFY, TCS, HDFCBANK, ICICIBANK, SBIN, LT, ADANIENT)
- Best for: Quick daily market checks
- Time: 2-3 minutes

**2. 🌐 Scan All NSE**
- Scans entire NSE market (~2000 stocks)
- Best for: Discovering new opportunities across all sectors
- Time: 10-15 minutes (adjust Workers if needed)

**3. 🔴 Scan Now**
- Scans immediately with your custom settings
- Best for: Specific watchlists or detailed analysis
- Customizable in the form below

### 📊 **Live Data Indicators**

- **Green pulsing dot**: Indicates fresh live data
- **Time indicator**: Shows how fresh the current data is ("just now", "5m ago", etc.)
- **Progress bar**: Shows scan completion in real-time

### 🎯 **Stock Selection Modes**

**Watchlist Mode** (Default)
- Pre-configured 8 stocks
- Quick and focused analysis

**All Stocks Mode**
- Full NSE universe
- Comprehensive market scanning
- Toggle between modes with buttons below the quick scans

### 📈 **Understanding Results**

Once you run a scan:

**Summary Cards (Top)**
- **Qualified**: Number of stocks passing quality filters
- **Avg Grade**: Average pre-market quality score (0-100)
- **Avg ML**: Machine learning confidence (0-1)
- **Horizons**: Split between intraday vs swing trades
- **Avg Event**: Event impact score

**Results Table**
- **Rank**: Trading priority
- **Stock**: Symbol name
- **Action**: BUY/SELL/WATCH
- **Horizon**: Intraday vs Swing
- **Grade**: Quality score
- **Confidence**: Strategy confidence %
- **ML**: Model probability

**Setup Detail (Right Panel)**
- Entry/Stop levels
- Target prices
- Trade reasoning
- Earnings dates
- **NEW**: Candlestick chart of recent price action

### 🔄 **Auto-Refresh Feature**

Check the "Live auto-refresh before market open" checkbox to:
- Automatically scan before market open
- Run every N minutes (configurable)
- Only active during pre-market hours (before 9:15 AM IST)

### 💾 **Saved Scans**

All your scans are automatically saved and appear in the left sidebar under "Saved Scans". Click any scan to:
- Reload past results
- Compare with current market conditions
- See new entrants, dropped setups, and grade movers

### 📊 **Compare Day View**

See what changed since your last scan:
- **🆕 New Entrants**: Stocks that just qualified
- **📈 Grade Movers**: Stocks with significant score changes
- **❌ Dropped Setups**: Stocks that are no longer qualified

### 📥 **Export Watchlist**

After running a scan, export results to your trading platform:
- **Export Intraday**: Download intraday-qualified stocks (CSV)
- **Export Swing**: Download swing-qualified stocks (CSV)

Include: Stock, Action, Entry, Stop Loss, Targets, Grade, Confidence

## Common Workflows

### **Daily Market Check (5 minutes)**
1. Click **⚡ Scan Watchlist**
2. Wait for results
3. Review top 5 setups in results table
4. Click any stock to see candlestick chart and details
5. Export to CSV if trading today

### **Weekly Opportunity Hunt (30 minutes)**
1. Click **🌐 Scan All NSE**
2. Sort results by Grade or Confidence
3. Review sector heatmap
4. Check Compare View for new opportunities
5. Save scan for future reference

### **Custom Analysis (15 minutes)**
1. Enter specific symbols in the textarea (space-separated)
2. Adjust parameters (Period, Interval, Top N, etc.)
3. Click **🔴 Scan Now Live**
4. Analyze setup detail for selected stocks
5. View candlestick charts for each stock

### **Continuous Monitoring**
1. Check "Live auto-refresh" before market open
2. Set refresh interval (e.g., 5 minutes)
3. UI will automatically update results
4. View latest data freshness indicator
5. Compare changes across multiple runs

## Parameter Guide

- **History Period**: How far back to analyze (3mo, 6mo, 1y)
- **Interval**: Candle timeframe (1d daily, 1h hourly)
- **Top Results**: Maximum setups to return
- **Workers**: Parallel processing threads (higher = faster, more CPU)
- **Candidate Pool**: First-pass screening size
- **Validation Pool**: Deep analysis on top candidates
- **Benchmark**: Market benchmark for comparison (^NSEI = Nifty 50)

## Tips for Best Results

✅ **DO:**
- Start with Watchlist mode for quick checks
- Use All Stocks mode during lower-volume periods
- Review candlestick charts before trading
- Compare with previous scans to spot trends
- Export and verify in your trading platform

❌ **DON'T:**
- Trade immediately without chart review
- Ignore the Stop Loss levels
- Rely solely on ML probability (cross-check with charts)
- Scan too frequently in live market (causes lag)
- Set Workers too high on low-spec machines

## Troubleshooting

**Scan takes too long?**
- Reduce Workers count (Trade speed for accuracy)
- Use Watchlist instead of All Stocks
- Close other applications

**No results showing?**
- Increase candidate pool and validation pool
- Uncheck "Strict shortlist" for more results
- Check internet connectivity for data fetching

**Auto-refresh not working?**
- Ensure it's checked
- Verify current time is before 9:15 AM IST
- Check refresh interval is at least 1 minute

## Next Steps

- 📖 Read full [README.md](README.md) for advanced features
- 🔧 Configure with [config.py](config.py)
- 📊 Set up scheduled daily scans: `python scheduled_scan.py --run-now`
- 📦 Build desktop app: `python build.py`

---

**Need help?** The UI includes tooltips on all buttons. Hover over any option for details.