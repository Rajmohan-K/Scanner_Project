CREATE TABLE IF NOT EXISTS daily_candles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    candle_date TEXT NOT NULL,
    provider TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS technical_indicators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    vwap REAL,
    ema9 REAL,
    ema20 REAL,
    ema50 REAL,
    rsi REAL,
    macd REAL,
    adx REAL,
    atr REAL,
    supertrend REAL,
    relative_volume REAL,
    sector_strength REAL,
    market_breadth REAL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scanner_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scanner_run_id TEXT,
    scan_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    rank INTEGER,
    score REAL,
    grade TEXT,
    decision TEXT,
    entry REAL,
    stop_loss REAL,
    target1 REAL,
    target2 REAL,
    target3 REAL,
    risk_reward REAL,
    confidence REAL,
    reason_selected TEXT,
    risk_warning TEXT,
    payload TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trade_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    scan_type TEXT,
    trade_type TEXT,
    entry_zone TEXT,
    stop_loss REAL,
    target1 REAL,
    target2 REAL,
    target3 REAL,
    risk_reward REAL,
    confidence REAL,
    invalidation_point TEXT,
    reasoning TEXT,
    payload TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS backtest_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    scan_type TEXT,
    strategy TEXT,
    win_rate REAL,
    profit_factor REAL,
    max_drawdown REAL,
    total_trades INTEGER,
    payload TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    actor TEXT,
    symbol TEXT,
    entity_type TEXT,
    entity_id TEXT,
    message TEXT,
    payload TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_daily_candles_symbol_date
ON daily_candles(symbol, candle_date DESC);

CREATE INDEX IF NOT EXISTS idx_technical_indicators_symbol_timeframe
ON technical_indicators(symbol, timeframe, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_scanner_results_type_rank
ON scanner_results(scan_type, rank, score DESC, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_scanner_results_symbol_type
ON scanner_results(symbol, scan_type, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_trade_plans_symbol_type
ON trade_plans(symbol, scan_type, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_backtest_results_symbol_type
ON backtest_results(symbol, scan_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_logs_event_created
ON audit_logs(event_type, created_at DESC);
