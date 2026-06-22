CREATE TABLE IF NOT EXISTS meta_scan_runs (
    id TEXT PRIMARY KEY,
    timeframe TEXT NOT NULL,
    status TEXT NOT NULL,
    generated_at TEXT,
    symbols_analyzed INTEGER DEFAULT 0,
    shown_count INTEGER DEFAULT 0,
    trade_count INTEGER DEFAULT 0,
    watch_count INTEGER DEFAULT 0,
    rejected_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS meta_scan_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meta_scan_run_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT,
    scan_types_matched TEXT,
    meta_score REAL,
    scanner_agreement_score REAL,
    ai_confidence REAL,
    ml_confidence REAL,
    risk_score REAL,
    backtest_score REAL,
    final_decision TEXT,
    trade_grade TEXT,
    should_show INTEGER DEFAULT 0,
    should_trade INTEGER DEFAULT 0,
    should_watch INTEGER DEFAULT 0,
    should_reject INTEGER DEFAULT 0,
    trade_plan TEXT,
    reason_selected TEXT,
    reason_rejected TEXT,
    data_freshness TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_meta_results_symbol
ON meta_scan_results(symbol, created_at DESC);

CREATE TABLE IF NOT EXISTS scanner_signal_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meta_scan_run_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    source_scan_id TEXT,
    scan_family TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scanner_conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meta_scan_run_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    warning TEXT NOT NULL,
    risk_score REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scanner_agreements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meta_scan_run_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    scan_types TEXT,
    agreement_score REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
