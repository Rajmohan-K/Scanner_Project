CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'analyst',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stocks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  sector TEXT NOT NULL,
  industry TEXT NOT NULL DEFAULT '',
  market_cap REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stocks_sector ON stocks(sector);
CREATE INDEX IF NOT EXISTS idx_stocks_symbol_name ON stocks(symbol, name);

CREATE TABLE IF NOT EXISTS stock_prices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  stock_id INTEGER NOT NULL REFERENCES stocks(id),
  price REAL NOT NULL,
  change_pct REAL NOT NULL DEFAULT 0,
  volume REAL NOT NULL DEFAULT 0,
  price_date TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stock_prices_stock_date ON stock_prices(stock_id, price_date);

CREATE TABLE IF NOT EXISTS market_indices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  value REAL NOT NULL,
  change_pct REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS financial_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  stock_id INTEGER UNIQUE NOT NULL REFERENCES stocks(id),
  pe REAL NOT NULL DEFAULT 0,
  peg REAL NOT NULL DEFAULT 0,
  roe REAL NOT NULL DEFAULT 0,
  roa REAL NOT NULL DEFAULT 0,
  roce REAL NOT NULL DEFAULT 0,
  debt_ratio REAL NOT NULL DEFAULT 0,
  dividend_yield REAL NOT NULL DEFAULT 0,
  revenue_growth REAL NOT NULL DEFAULT 0,
  eps_growth REAL NOT NULL DEFAULT 0,
  net_profit_margin REAL NOT NULL DEFAULT 0,
  free_cash_flow REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_financial_metrics_growth ON financial_metrics(revenue_growth, eps_growth);

CREATE TABLE IF NOT EXISTS profitability_scores (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  stock_id INTEGER UNIQUE NOT NULL REFERENCES stocks(id),
  profitability_score REAL NOT NULL,
  growth_score REAL NOT NULL,
  value_score REAL NOT NULL,
  momentum_score REAL NOT NULL,
  risk_score REAL NOT NULL,
  quality_score REAL NOT NULL,
  final_ai_score REAL NOT NULL,
  explanation TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_profitability_scores_final ON profitability_scores(final_ai_score DESC);

CREATE TABLE IF NOT EXISTS ai_recommendations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  stock_id INTEGER NOT NULL REFERENCES stocks(id),
  rating TEXT NOT NULL,
  confidence REAL NOT NULL,
  reasoning TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_recommendations_rating ON ai_recommendations(rating, confidence DESC);

CREATE TABLE IF NOT EXISTS ai_insights (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  stock_id INTEGER REFERENCES stocks(id),
  scan_type TEXT NOT NULL DEFAULT '',
  insight_type TEXT NOT NULL,
  recommendation TEXT NOT NULL,
  confidence_score REAL NOT NULL DEFAULT 0,
  risk_score REAL NOT NULL DEFAULT 0,
  opportunity_score REAL NOT NULL DEFAULT 0,
  summary TEXT NOT NULL,
  reasons_json TEXT NOT NULL DEFAULT '[]',
  risks_json TEXT NOT NULL DEFAULT '[]',
  signals_json TEXT NOT NULL DEFAULT '[]',
  data_freshness TEXT NOT NULL DEFAULT '',
  generated_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_insights_stock ON ai_insights(stock_id, generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_insights_type ON ai_insights(insight_type, generated_at DESC);

CREATE TABLE IF NOT EXISTS ai_trade_plans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  stock_id INTEGER REFERENCES stocks(id),
  scan_type TEXT NOT NULL DEFAULT '',
  trade_type TEXT NOT NULL,
  entry_zone TEXT NOT NULL DEFAULT '',
  stop_loss REAL,
  target1 REAL,
  target2 REAL,
  target3 REAL,
  risk_reward REAL NOT NULL DEFAULT 0,
  confidence_score REAL NOT NULL DEFAULT 0,
  setup_type TEXT NOT NULL DEFAULT '',
  reasoning TEXT NOT NULL DEFAULT '',
  invalidation_point TEXT NOT NULL DEFAULT '',
  timeframe TEXT NOT NULL DEFAULT '',
  generated_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_trade_plans_stock ON ai_trade_plans(stock_id, generated_at DESC);

CREATE TABLE IF NOT EXISTS ai_user_queries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER REFERENCES users(id),
  query TEXT NOT NULL,
  response TEXT NOT NULL,
  context_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlists (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  watchlist_id INTEGER NOT NULL REFERENCES watchlists(id),
  stock_id INTEGER NOT NULL REFERENCES stocks(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(watchlist_id, stock_id)
);

CREATE TABLE IF NOT EXISTS portfolios (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_holdings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  portfolio_id INTEGER NOT NULL REFERENCES portfolios(id),
  stock_id INTEGER NOT NULL REFERENCES stocks(id),
  quantity REAL NOT NULL,
  average_price REAL NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  stock_id INTEGER REFERENCES stocks(id),
  alert_type TEXT NOT NULL,
  condition TEXT NOT NULL,
  threshold REAL NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_active ON alerts(active, alert_type);

CREATE TABLE IF NOT EXISTS news_articles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  stock_id INTEGER REFERENCES stocks(id),
  title TEXT NOT NULL,
  category TEXT NOT NULL,
  source TEXT NOT NULL,
  url TEXT NOT NULL DEFAULT '',
  published_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_news_published ON news_articles(published_at DESC);

CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  name TEXT NOT NULL,
  report_type TEXT NOT NULL,
  path TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backtests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  name TEXT NOT NULL,
  strategy TEXT NOT NULL,
  win_rate REAL NOT NULL DEFAULT 0,
  profit_factor REAL NOT NULL DEFAULT 0,
  max_drawdown REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  stock_id INTEGER NOT NULL REFERENCES stocks(id),
  side TEXT NOT NULL,
  quantity REAL NOT NULL,
  entry_price REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_settings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER UNIQUE NOT NULL REFERENCES users(id),
  theme TEXT NOT NULL DEFAULT 'quantum',
  density TEXT NOT NULL DEFAULT 'analyst',
  notifications_enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS saved_scanners (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  name TEXT NOT NULL,
  config_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS saved_filters (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  name TEXT NOT NULL,
  filter_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
