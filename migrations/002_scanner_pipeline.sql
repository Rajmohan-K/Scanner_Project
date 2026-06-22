CREATE TABLE IF NOT EXISTS scan_runs (
    id TEXT PRIMARY KEY,
    scan_type TEXT NOT NULL,
    scan_family TEXT NOT NULL,
    scanner_bucket TEXT NOT NULL,
    pipeline_stage TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    source_scan_id TEXT,
    started_at TEXT,
    completed_at TEXT,
    total_candidates INTEGER DEFAULT 0,
    selected_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_scan_runs_family_created
ON scan_runs(scan_family, created_at DESC);

CREATE TABLE IF NOT EXISTS premarket_scan_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    previous_close REAL,
    premarket_price REAL,
    gap_percent REAL,
    premarket_volume REAL,
    relative_volume REAL,
    news_score REAL,
    sector_score REAL,
    liquidity_score REAL,
    risk_score REAL,
    premarket_score REAL,
    decision TEXT,
    reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_premarket_results_run_score
ON premarket_scan_results(scan_run_id, premarket_score DESC);

CREATE TABLE IF NOT EXISTS open_confirmation_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id TEXT NOT NULL,
    premarket_result_id INTEGER,
    symbol TEXT NOT NULL,
    open_price REAL,
    price_at_0908 REAL,
    gap_hold_percent REAL,
    vwap_status TEXT,
    opening_volume REAL,
    relative_volume REAL,
    confirmation_score REAL,
    risk_score REAL,
    decision TEXT,
    reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_open_confirmation_run_score
ON open_confirmation_results(scan_run_id, confirmation_score DESC);

CREATE TABLE IF NOT EXISTS intraday_scan_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id TEXT NOT NULL,
    open_confirmation_id INTEGER,
    symbol TEXT NOT NULL,
    current_price REAL,
    trade_direction TEXT,
    entry_zone_low REAL,
    entry_zone_high REAL,
    stop_loss REAL,
    target_1 REAL,
    target_2 REAL,
    target_3 REAL,
    risk_reward_ratio REAL,
    trend_score REAL,
    volume_score REAL,
    technical_score REAL,
    sector_score REAL,
    backtest_score REAL,
    ml_score REAL,
    risk_score REAL,
    intraday_score REAL,
    trade_grade TEXT,
    decision TEXT,
    reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_intraday_results_run_score
ON intraday_scan_results(scan_run_id, intraday_score DESC);
