CREATE TABLE IF NOT EXISTS live_quotes (
    symbol TEXT PRIMARY KEY,
    price REAL,
    previous_close REAL,
    change_pct REAL,
    volume REAL,
    provider TEXT,
    market_status TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS intraday_candles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    candle_time TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS indicator_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    scan_type TEXT NOT NULL,
    vwap REAL,
    ema9 REAL,
    ema20 REAL,
    ema50 REAL,
    rsi REAL,
    macd REAL,
    adx REAL,
    atr REAL,
    supertrend REAL,
    volume_ratio REAL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scanner_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    score REAL,
    grade TEXT,
    rank INTEGER,
    decision TEXT,
    reason TEXT,
    payload TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS opportunity_rankings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bucket TEXT NOT NULL,
    symbol TEXT NOT NULL,
    rank INTEGER NOT NULL,
    score REAL,
    grade TEXT,
    risk_score REAL,
    confidence_score REAL,
    sector TEXT,
    payload TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_insight_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    insight_type TEXT NOT NULL,
    title TEXT,
    rating TEXT,
    confidence_score REAL,
    reason TEXT,
    payload TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ml_prediction_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    scan_type TEXT,
    prediction TEXT,
    confidence_score REAL,
    risk_score REAL,
    payload TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta_score_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    scan_types_matched TEXT,
    meta_score REAL,
    ai_confidence REAL,
    ml_confidence REAL,
    risk_score REAL,
    final_decision TEXT,
    payload TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_live_quotes_updated
ON live_quotes(updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_live_quotes_symbol_updated
ON live_quotes(symbol, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_intraday_candles_symbol_interval_time
ON intraday_candles(symbol, interval, candle_time DESC);

CREATE INDEX IF NOT EXISTS idx_indicator_snapshots_symbol_scan_updated
ON indicator_snapshots(symbol, scan_type, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_scanner_snapshots_scan_score
ON scanner_snapshots(scan_type, score DESC, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_scanner_snapshots_symbol_scan
ON scanner_snapshots(symbol, scan_type, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_opportunity_rankings_bucket_rank
ON opportunity_rankings(bucket, rank, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_opportunity_rankings_score
ON opportunity_rankings(score DESC, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_opportunity_rankings_sector
ON opportunity_rankings(sector, score DESC);

CREATE INDEX IF NOT EXISTS idx_opportunity_rankings_risk_confidence
ON opportunity_rankings(risk_score, confidence_score DESC);

CREATE INDEX IF NOT EXISTS idx_ai_insight_snapshots_symbol_updated
ON ai_insight_snapshots(symbol, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_ml_prediction_snapshots_symbol_scan
ON ml_prediction_snapshots(symbol, scan_type, confidence_score DESC, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_meta_score_snapshots_symbol_score
ON meta_score_snapshots(symbol, meta_score DESC, updated_at DESC);
