import os
import json
import psycopg2
import psycopg2.pool
import psycopg2.extras
from utils.logger import logger

class MockCursor:
    def __init__(self, description=None, rows=None, rowcount=0, lastrowid=None):
        self.description = description or []
        self.rows = rows or []
        self.rowcount = len(rows) if rows else rowcount
        self.lastrowid = lastrowid or 1
        self._index = 0
        
    def execute(self, query, params=None):
        pass
        
    def fetchall(self):
        return self.rows
        
    def fetchone(self):
        if self._index < len(self.rows):
            r = self.rows[self._index]
            self._index += 1
            return r
        return None


_SHARED_MOCK_DB = None

def get_shared_mock_db():
    global _SHARED_MOCK_DB
    if _SHARED_MOCK_DB is None:
        _SHARED_MOCK_DB = {
            "users": [
                {"id": 1, "email": "analyst@scanner.local", "name": "Default Analyst", "role": "admin", "created_at": "2026-06-25T00:00:00", "updated_at": "2026-06-25T00:00:00"}
            ],
            "watchlists": [
                {"id": 1, "user_id": 1, "name": "My Watchlist", "created_at": "2026-06-25T00:00:00", "updated_at": "2026-06-25T00:00:00"}
            ],
            "portfolios": [
                {"id": 1, "user_id": 1, "name": "Core Portfolio", "created_at": "2026-06-25T00:00:00", "updated_at": "2026-06-25T00:00:00"}
            ],
            "user_settings": [
                {"id": 1, "user_id": 1, "theme": "quantum", "density": "analyst", "notifications_enabled": 1, "created_at": "2026-06-25T00:00:00", "updated_at": "2026-06-25T00:00:00"}
            ],
            "stocks": [
                {"id": 1, "symbol": "RELIANCE", "name": "Reliance Industries", "sector": "Energy", "industry": "Refining", "market_cap": 1700000.0, "created_at": "2026-06-25T00:00:00", "updated_at": "2026-06-25T00:00:00"},
                {"id": 2, "symbol": "INFY", "name": "Infosys Ltd", "sector": "Technology", "industry": "IT Services", "market_cap": 600000.0, "created_at": "2026-06-25T00:00:00", "updated_at": "2026-06-25T00:00:00"},
                {"id": 3, "symbol": "HDFCBANK", "name": "HDFC Bank Ltd", "sector": "Finance", "industry": "Banking", "market_cap": 900000.0, "created_at": "2026-06-25T00:00:00", "updated_at": "2026-06-25T00:00:00"}
            ],
            "market_indices": [
                {"id": 1, "symbol": "^NSEI", "name": "NIFTY 50", "value": 23500.0, "change_pct": 0.45, "created_at": "2026-06-25T00:00:00", "updated_at": "2026-06-25T00:00:00"},
                {"id": 2, "symbol": "^BSESN", "name": "SENSEX", "value": 77200.0, "change_pct": 0.41, "created_at": "2026-06-25T00:00:00", "updated_at": "2026-06-25T00:00:00"}
            ],
            "financial_metrics": [
                {"id": 1, "stock_id": 1, "pe": 25.4, "peg": 1.2, "roe": 14.5, "roa": 8.2, "roce": 15.1, "debt_ratio": 0.35, "dividend_yield": 0.8, "revenue_growth": 12.0, "eps_growth": 10.5, "net_profit_margin": 11.2, "free_cash_flow": 50000.0, "created_at": "2026-06-25T00:00:00", "updated_at": "2026-06-25T00:00:00"},
                {"id": 2, "stock_id": 2, "pe": 28.1, "peg": 1.5, "roe": 22.0, "roa": 15.0, "roce": 25.0, "debt_ratio": 0.05, "dividend_yield": 2.1, "revenue_growth": 8.5, "eps_growth": 7.2, "net_profit_margin": 18.5, "free_cash_flow": 20000.0, "created_at": "2026-06-25T00:00:00", "updated_at": "2026-06-25T00:00:00"},
                {"id": 3, "stock_id": 3, "pe": 18.5, "peg": 0.9, "roe": 17.2, "roa": 2.1, "roce": 18.0, "debt_ratio": 0.85, "dividend_yield": 1.1, "revenue_growth": 15.0, "eps_growth": 16.0, "net_profit_margin": 20.2, "free_cash_flow": 35000.0, "created_at": "2026-06-25T00:00:00", "updated_at": "2026-06-25T00:00:00"}
            ],
            "profitability_scores": [
                {"id": 1, "stock_id": 1, "profitability_score": 82.0, "growth_score": 75.0, "value_score": 65.0, "momentum_score": 70.0, "risk_score": 30.0, "quality_score": 80.0, "final_ai_score": 78.5, "explanation": "Strong fundamental backing", "created_at": "2026-06-25T00:00:00", "updated_at": "2026-06-25T00:00:00"},
                {"id": 2, "stock_id": 2, "profitability_score": 88.0, "growth_score": 70.0, "value_score": 60.0, "momentum_score": 75.0, "risk_score": 25.0, "quality_score": 85.0, "final_ai_score": 81.2, "explanation": "High quality tech sector lead", "created_at": "2026-06-25T00:00:00", "updated_at": "2026-06-25T00:00:00"},
                {"id": 3, "stock_id": 3, "profitability_score": 80.0, "growth_score": 82.0, "value_score": 75.0, "momentum_score": 68.0, "risk_score": 40.0, "quality_score": 78.0, "final_ai_score": 79.8, "explanation": "Valuation looks reasonable", "created_at": "2026-06-25T00:00:00", "updated_at": "2026-06-25T00:00:00"}
            ],
            "ai_recommendations": [
                {"id": 1, "stock_id": 1, "rating": "Buy", "confidence": 78.5, "reasoning": "Energy leader", "created_at": "2026-06-25T00:00:00", "updated_at": "2026-06-25T00:00:00"},
                {"id": 2, "stock_id": 2, "rating": "Buy", "confidence": 81.2, "reasoning": "Strong ROE", "created_at": "2026-06-25T00:00:00", "updated_at": "2026-06-25T00:00:00"},
                {"id": 3, "stock_id": 3, "rating": "Buy", "confidence": 79.8, "reasoning": "Undervalued bank", "created_at": "2026-06-25T00:00:00", "updated_at": "2026-06-25T00:00:00"}
            ],
            "stock_prices": [
                {"id": 1, "stock_id": 1, "price": 2450.0, "change_pct": 0.8, "volume": 5000000.0, "price_date": "2026-06-25", "created_at": "2026-06-25T00:00:00", "updated_at": "2026-06-25T00:00:00"},
                {"id": 2, "stock_id": 2, "price": 1420.0, "change_pct": -0.3, "volume": 3000000.0, "price_date": "2026-06-25", "created_at": "2026-06-25T00:00:00", "updated_at": "2026-06-25T00:00:00"},
                {"id": 3, "stock_id": 3, "price": 1600.0, "change_pct": 1.2, "volume": 8000000.0, "price_date": "2026-06-25", "created_at": "2026-06-25T00:00:00", "updated_at": "2026-06-25T00:00:00"}
            ],
            "watchlist_items": [],
            "alerts": [],
            "news_articles": [],
            "reports": [],
            "backtests": [],
            "paper_trades": [],
            "saved_scanners": [],
            "saved_filters": [],
            "opportunity_rankings": [],
            "company_symbol_registry": [],
            "signal_records": []
        }
    return _SHARED_MOCK_DB

class MockConnection:
    def __init__(self):
        self._db = get_shared_mock_db()

    def cursor(self):
        return MockCursor(rows=[])
        
    def execute(self, query, params=None):
        import re
        query = translate_query(query)
        query_strip = query.strip()
        
        # 1. Handle INSERT
        insert_match = re.search(r"INSERT\s+INTO\s+(\w+)\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)", query_strip, re.IGNORECASE | re.DOTALL)
        if insert_match:
            table_name = insert_match.group(1).lower()
            cols = [c.strip() for c in insert_match.group(2).split(",")]
            if table_name not in self._db:
                self._db[table_name] = []
            row = {}
            for col, val in zip(cols, params or ()):
                row[col] = val
            self._db[table_name].append(row)
            return MockCursor(rowcount=1)
            
        # 2. Handle UPDATE
        update_match = re.match(r"UPDATE\s+(\w+)\s+SET\s+(.+?)\s+WHERE\s+(.+)$", query_strip, re.IGNORECASE | re.DOTALL)
        if update_match:
            table_name = update_match.group(1).lower()
            set_clause = update_match.group(2)
            where_clause = update_match.group(3)
            
            set_cols = re.findall(r"(\w+)\s*=\s*(?:\?|%s)", set_clause)
            where_cols = re.findall(r"(\w+)\s*=\s*(?:\?|%s)", where_clause)
            
            num_set = len(set_cols)
            set_vals = params[:num_set] if params else []
            where_vals = params[num_set:] if params else []
            
            if table_name in self._db:
                for row in self._db[table_name]:
                    matched = True
                    for col, val in zip(where_cols, where_vals):
                        if row.get(col) != val:
                            matched = False
                            break
                    if matched:
                        for col, val in zip(set_cols, set_vals):
                            row[col] = val
            return MockCursor(rowcount=1)
            
        # 3. Handle DELETE
        delete_match = re.match(r"DELETE\s+FROM\s+(\w+)(?:\s+WHERE\s+(.+))?$", query_strip, re.IGNORECASE | re.DOTALL)
        if delete_match:
            table_name = delete_match.group(1).lower()
            where_clause = delete_match.group(2) if len(delete_match.groups()) >= 2 and delete_match.group(2) else None
            
            if table_name in self._db:
                if not where_clause:
                    self._db[table_name] = []
                else:
                    where_cols = re.findall(r"(\w+)\s*=\s*(?:\?|%s)", where_clause)
                    self._db[table_name] = [
                        row for row in self._db[table_name]
                        if not all(row.get(col) == val for col, val in zip(where_cols, params or ()))
                    ]
            return MockCursor(rowcount=1)
            
        # 4. Handle SELECT
        select_match = re.search(r"FROM\s+(\w+)", query_strip, re.IGNORECASE)
        if select_match:
            table_name = select_match.group(1).lower()
            if table_name in self._db:
                data = self._db[table_name]
                if table_name == "stocks" and "financial_metrics" in query:
                    joined = []
                    for s in self._db["stocks"]:
                        fm = next((x for x in self._db["financial_metrics"] if x["stock_id"] == s["id"]), {})
                        ps = next((x for x in self._db["profitability_scores"] if x["stock_id"] == s["id"]), {})
                        ar = next((x for x in self._db["ai_recommendations"] if x["stock_id"] == s["id"]), {})
                        sp = next((x for x in self._db["stock_prices"] if x["stock_id"] == s["id"]), {})
                        joined.append({
                            **s, **fm, **ps, **ar,
                            "live_price": sp.get("price"),
                            "change_pct": sp.get("change_pct"),
                            "volume": sp.get("volume"),
                            "ai_rating": ar.get("rating"),
                            "ai_confidence": ar.get("confidence"),
                            "pe": fm.get("pe"),
                            "roe": fm.get("roe"),
                            "revenue_growth": fm.get("revenue_growth"),
                            "eps_growth": fm.get("eps_growth"),
                            "net_profit_margin": fm.get("net_profit_margin"),
                            "free_cash_flow": fm.get("free_cash_flow"),
                            "profitability_score": ps.get("profitability_score"),
                            "growth_score": ps.get("growth_score"),
                            "value_score": ps.get("value_score"),
                            "momentum_score": ps.get("momentum_score"),
                            "risk_score": ps.get("risk_score"),
                            "quality_score": ps.get("quality_score"),
                            "final_ai_score": ps.get("final_ai_score"),
                            "explanation": ps.get("explanation"),
                            "reasoning": ar.get("reasoning")
                        })
                    return MockCursor(rows=joined)
                else:
                    rows = []
                    for r in data:
                        keep = True
                        if "signal_id LIKE" in query_strip:
                            val = params[0] if params else ""
                            val_clean = val.replace("%", "")
                            if not r.get("signal_id", "").startswith(val_clean):
                                keep = False
                        if "scan_family LIKE" in query_strip or "scan_family like" in query_strip.lower():
                            term = ""
                            for p in params or ():
                                if isinstance(p, str) and "%" in p:
                                    term = p.replace("%", "").replace("_", "-").lower()
                                    break
                            if term:
                                match_found = False
                                for col in ("scan_family", "scanner_bucket", "pipeline_stage", "scan_type"):
                                    val = str(r.get(col) or "").lower().replace("_", "-")
                                    if term in val:
                                        match_found = True
                                        break
                                if not match_found:
                                    keep = False
                        if "NOT IN ('CLOSED', 'STOP LOSS HIT', 'TARGET HIT')" in query_strip.upper():
                            status = str(r.get("status", "")).upper()
                            if status in ('CLOSED', 'STOP LOSS HIT', 'TARGET HIT'):
                                keep = False
                        elif "IN ('CLOSED', 'STOP LOSS HIT', 'TARGET HIT')" in query_strip.upper():
                            status = str(r.get("status", "")).upper()
                            if status not in ('CLOSED', 'STOP LOSS HIT', 'TARGET HIT'):
                                keep = False
                        
                        where_part = re.search(r"WHERE\s+(.+)$", query_strip, re.IGNORECASE | re.DOTALL)
                        if where_part:
                            where_clause = where_part.group(1)
                            if "IN" not in where_clause.upper() and "LIKE" not in where_clause.upper():
                                where_cols = re.findall(r"(\w+)\s*=\s*(?:\?|%s)", where_clause)
                                if where_cols and params:
                                    for col, val in zip(where_cols, params):
                                        if r.get(col) != val:
                                            keep = False
                                            break
                        if keep:
                            rows.append(r)
                            
                    # Handle ORDER BY archived_at DESC
                    if "ORDER BY archived_at DESC" in query_strip.upper():
                        rows = sorted(rows, key=lambda x: x.get("archived_at", ""), reverse=True)
                    return MockCursor(rows=rows)
                    
        return MockCursor(rows=[])
        
    def commit(self):
        pass
        
    def rollback(self):
        pass
        
    def close(self):
        pass
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class PSQLConnectionAdapter:
    def __init__(self, conn, pool=None):
        self._conn = conn
        self._pool = pool
        
    def cursor(self, *args, **kwargs):
        return self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
    def execute(self, query, params=None):
        query = translate_query(query)
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(query, params or ())
        return cur
        
    def commit(self):
        self._conn.commit()
        
    def rollback(self):
        self._conn.rollback()
        
    def close(self):
        if self._pool:
            self._pool.putconn(self._conn)
        else:
            self._conn.close()
            
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()


_pg_pool = None

def get_pg_pool():
    global _pg_pool
    if _pg_pool is not None:
        return _pg_pool
    
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/scanner")
    try:
        conn = psycopg2.connect(db_url, connect_timeout=2)
        conn.close()
        _pg_pool = psycopg2.pool.SimpleConnectionPool(1, 20, db_url)
        logger.info(f"Connected to PostgreSQL pool at {db_url}")
    except Exception as e:
        logger.warning(f"Could not connect to PostgreSQL at {db_url}: {e}. Falling back to MockConnection.")
        _pg_pool = "MOCK"
    return _pg_pool


def translate_query(query: str) -> str:
    query = query.replace("?", "%s")
    if "INSERT OR IGNORE INTO" in query:
        query = query.replace("INSERT OR IGNORE INTO", "INSERT INTO")
        if "ON CONFLICT" not in query:
            query = query + " ON CONFLICT DO NOTHING"
    if "INSERT OR REPLACE INTO" in query:
        query = query.replace("INSERT OR REPLACE INTO", "INSERT INTO")
    if "sqlite_master" in query:
        query = query.replace("sqlite_master", "information_schema.tables")
        query = query.replace("name FROM", "table_name FROM")
        query = query.replace("type='table'", "table_schema='public'")
        query = query.replace("name IN", "table_name IN")
        query = query.replace("name='", "table_name='")
    return query


def rows(query: str, params: tuple = ()) -> list[dict]:
    pool = get_pg_pool()
    if pool == "MOCK":
        conn = MockConnection()
        cur = conn.execute(query, params)
        return [dict(r) for r in cur.fetchall()]
        
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(translate_query(query), params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        pool.putconn(conn)


def execute(query: str, params: tuple = ()) -> dict:
    pool = get_pg_pool()
    if pool == "MOCK":
        return {"lastrowid": 1, "rowcount": 1}
        
    conn = pool.getconn()
    try:
        query = translate_query(query)
        with conn.cursor() as cur:
            cur.execute(query, params)
            lastrowid = None
            try:
                if query.strip().upper().startswith("INSERT"):
                    try:
                        cur.execute("SAVEPOINT lastval_sp;")
                        cur.execute("SELECT lastval();")
                        lastrowid = cur.fetchone()[0]
                        cur.execute("RELEASE SAVEPOINT lastval_sp;")
                    except Exception:
                        try:
                            cur.execute("ROLLBACK TO SAVEPOINT lastval_sp;")
                        except Exception:
                            pass
            except Exception:
                pass
            conn.commit()
            return {"lastrowid": lastrowid or 1, "rowcount": cur.rowcount}
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def ensure_pg_db():
    pool = get_pg_pool()
    if pool == "MOCK":
        return
        
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                  id SERIAL PRIMARY KEY,
                  email VARCHAR(255) UNIQUE NOT NULL,
                  name VARCHAR(255) NOT NULL,
                  role VARCHAR(50) NOT NULL DEFAULT 'analyst',
                  created_at VARCHAR(50) NOT NULL,
                  updated_at VARCHAR(50) NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS stocks (
                  id SERIAL PRIMARY KEY,
                  symbol VARCHAR(50) UNIQUE NOT NULL,
                  name VARCHAR(255) NOT NULL,
                  sector VARCHAR(255) NOT NULL,
                  industry VARCHAR(255) NOT NULL DEFAULT '',
                  market_cap DOUBLE PRECISION NOT NULL DEFAULT 0,
                  created_at VARCHAR(50) NOT NULL,
                  updated_at VARCHAR(50) NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS stock_prices (
                  id SERIAL PRIMARY KEY,
                  stock_id INTEGER NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
                  price DOUBLE PRECISION NOT NULL,
                  change_pct DOUBLE PRECISION NOT NULL DEFAULT 0,
                  volume DOUBLE PRECISION NOT NULL DEFAULT 0,
                  price_date VARCHAR(50) NOT NULL,
                  created_at VARCHAR(50) NOT NULL,
                  updated_at VARCHAR(50) NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS market_indices (
                  id SERIAL PRIMARY KEY,
                  symbol VARCHAR(50) UNIQUE NOT NULL,
                  name VARCHAR(255) NOT NULL,
                  value DOUBLE PRECISION NOT NULL,
                  change_pct DOUBLE PRECISION NOT NULL DEFAULT 0,
                  created_at VARCHAR(50) NOT NULL,
                  updated_at VARCHAR(50) NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS financial_metrics (
                  id SERIAL PRIMARY KEY,
                  stock_id INTEGER UNIQUE NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
                  pe DOUBLE PRECISION NOT NULL DEFAULT 0,
                  peg DOUBLE PRECISION NOT NULL DEFAULT 0,
                  roe DOUBLE PRECISION NOT NULL DEFAULT 0,
                  roa DOUBLE PRECISION NOT NULL DEFAULT 0,
                  roce DOUBLE PRECISION NOT NULL DEFAULT 0,
                  debt_ratio DOUBLE PRECISION NOT NULL DEFAULT 0,
                  dividend_yield DOUBLE PRECISION NOT NULL DEFAULT 0,
                  revenue_growth DOUBLE PRECISION NOT NULL DEFAULT 0,
                  eps_growth DOUBLE PRECISION NOT NULL DEFAULT 0,
                  net_profit_margin DOUBLE PRECISION NOT NULL DEFAULT 0,
                  free_cash_flow DOUBLE PRECISION NOT NULL DEFAULT 0,
                  created_at VARCHAR(50) NOT NULL,
                  updated_at VARCHAR(50) NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS profitability_scores (
                  id SERIAL PRIMARY KEY,
                  stock_id INTEGER UNIQUE NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
                  profitability_score DOUBLE PRECISION NOT NULL,
                  growth_score DOUBLE PRECISION NOT NULL,
                  value_score DOUBLE PRECISION NOT NULL,
                  momentum_score DOUBLE PRECISION NOT NULL,
                  risk_score DOUBLE PRECISION NOT NULL,
                  quality_score DOUBLE PRECISION NOT NULL,
                  final_ai_score DOUBLE PRECISION NOT NULL,
                  explanation TEXT NOT NULL,
                  created_at VARCHAR(50) NOT NULL,
                  updated_at VARCHAR(50) NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ai_recommendations (
                  id SERIAL PRIMARY KEY,
                  stock_id INTEGER NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
                  rating VARCHAR(50) NOT NULL,
                  confidence DOUBLE PRECISION NOT NULL,
                  reasoning TEXT NOT NULL,
                  created_at VARCHAR(50) NOT NULL,
                  updated_at VARCHAR(50) NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS watchlists (
                  id SERIAL PRIMARY KEY,
                  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  name VARCHAR(255) NOT NULL,
                  created_at VARCHAR(50) NOT NULL,
                  updated_at VARCHAR(50) NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS watchlist_items (
                  id SERIAL PRIMARY KEY,
                  watchlist_id INTEGER NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
                  stock_id INTEGER NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
                  created_at VARCHAR(50) NOT NULL,
                  updated_at VARCHAR(50) NOT NULL,
                  UNIQUE(watchlist_id, stock_id)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS portfolios (
                  id SERIAL PRIMARY KEY,
                  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  name VARCHAR(255) NOT NULL,
                  created_at VARCHAR(50) NOT NULL,
                  updated_at VARCHAR(50) NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_holdings (
                  id SERIAL PRIMARY KEY,
                  portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
                  stock_id INTEGER NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
                  quantity DOUBLE PRECISION NOT NULL,
                  average_price DOUBLE PRECISION NOT NULL,
                  created_at VARCHAR(50) NOT NULL,
                  updated_at VARCHAR(50) NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                  id SERIAL PRIMARY KEY,
                  user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  theme VARCHAR(50) NOT NULL DEFAULT 'quantum',
                  density VARCHAR(50) NOT NULL DEFAULT 'analyst',
                  notifications_enabled INTEGER NOT NULL DEFAULT 1,
                  created_at VARCHAR(50) NOT NULL,
                  updated_at VARCHAR(50) NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS saved_scanners (
                  id SERIAL PRIMARY KEY,
                  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  name VARCHAR(255) NOT NULL,
                  config_json TEXT NOT NULL,
                  created_at VARCHAR(50) NOT NULL,
                  updated_at VARCHAR(50) NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS saved_filters (
                  id SERIAL PRIMARY KEY,
                  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  name VARCHAR(255) NOT NULL,
                  filter_json TEXT NOT NULL,
                  created_at VARCHAR(50) NOT NULL,
                  updated_at VARCHAR(50) NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                  id SERIAL PRIMARY KEY,
                  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  stock_id INTEGER REFERENCES stocks(id) ON DELETE SET NULL,
                  alert_type VARCHAR(50) NOT NULL,
                  condition VARCHAR(50) NOT NULL,
                  threshold DOUBLE PRECISION NOT NULL DEFAULT 0,
                  active INTEGER NOT NULL DEFAULT 1,
                  created_at VARCHAR(50) NOT NULL,
                  updated_at VARCHAR(50) NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS news_articles (
                  id SERIAL PRIMARY KEY,
                  stock_id INTEGER REFERENCES stocks(id) ON DELETE SET NULL,
                  title VARCHAR(500) NOT NULL,
                  category VARCHAR(100) NOT NULL,
                  source VARCHAR(100) NOT NULL,
                  url VARCHAR(500) NOT NULL DEFAULT '',
                  published_at VARCHAR(50) NOT NULL,
                  created_at VARCHAR(50) NOT NULL,
                  updated_at VARCHAR(50) NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                  id SERIAL PRIMARY KEY,
                  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  name VARCHAR(255) NOT NULL,
                  report_type VARCHAR(100) NOT NULL,
                  path VARCHAR(500) NOT NULL DEFAULT '',
                  created_at VARCHAR(50) NOT NULL,
                  updated_at VARCHAR(50) NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS backtests (
                  id SERIAL PRIMARY KEY,
                  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  name VARCHAR(255) NOT NULL,
                  strategy VARCHAR(255) NOT NULL,
                  win_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
                  profit_factor DOUBLE PRECISION NOT NULL DEFAULT 0,
                  max_drawdown DOUBLE PRECISION NOT NULL DEFAULT 0,
                  created_at VARCHAR(50) NOT NULL,
                  updated_at VARCHAR(50) NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS paper_trades (
                  id SERIAL PRIMARY KEY,
                  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  stock_id INTEGER NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
                  side VARCHAR(10) NOT NULL,
                  quantity DOUBLE PRECISION NOT NULL,
                  entry_price DOUBLE PRECISION NOT NULL,
                  status VARCHAR(20) NOT NULL DEFAULT 'open',
                  created_at VARCHAR(50) NOT NULL,
                  updated_at VARCHAR(50) NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scan_runs (
                  id VARCHAR(100) PRIMARY KEY,
                  scan_type VARCHAR(100) NOT NULL,
                  scan_family VARCHAR(100) NOT NULL,
                  scanner_bucket VARCHAR(100) NOT NULL,
                  pipeline_stage VARCHAR(100) NOT NULL,
                  status VARCHAR(50) NOT NULL DEFAULT 'queued',
                  source_scan_id VARCHAR(100),
                  started_at VARCHAR(50),
                  completed_at VARCHAR(50),
                  total_candidates INTEGER DEFAULT 0,
                  selected_count INTEGER DEFAULT 0,
                  message TEXT,
                  report_path TEXT,
                  symbols_scanned INTEGER DEFAULT 0,
                  candidates_considered INTEGER DEFAULT 0,
                  summary_json TEXT,
                  scan_params_json TEXT,
                  payload_json TEXT,
                  archive_scan_id TEXT,
                  created_at VARCHAR(50) DEFAULT CURRENT_TIMESTAMP,
                  updated_at VARCHAR(50) DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scanner_results (
                  id SERIAL PRIMARY KEY,
                  scanner_run_id VARCHAR(100),
                  scan_type VARCHAR(100) NOT NULL,
                  symbol VARCHAR(50) NOT NULL,
                  rank INTEGER,
                  score DOUBLE PRECISION,
                  grade VARCHAR(10),
                  decision VARCHAR(100),
                  entry DOUBLE PRECISION,
                  stop_loss DOUBLE PRECISION,
                  target1 DOUBLE PRECISION,
                  target2 DOUBLE PRECISION,
                  target3 DOUBLE PRECISION,
                  risk_reward DOUBLE PRECISION,
                  confidence DOUBLE PRECISION,
                  reason_selected TEXT,
                  risk_warning TEXT,
                  payload TEXT,
                  scan_family VARCHAR(100),
                  scanner_bucket VARCHAR(100),
                  pipeline_stage VARCHAR(100),
                  result_bucket VARCHAR(100),
                  result_role VARCHAR(100),
                  score_json TEXT,
                  reasons_json TEXT,
                  risk_json TEXT,
                  trade_plan_json TEXT,
                  reason_rejected TEXT,
                  created_at VARCHAR(50),
                  updated_at VARCHAR(50) NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trade_plans (
                  id SERIAL PRIMARY KEY,
                  symbol VARCHAR(50) NOT NULL,
                  scan_type VARCHAR(100),
                  trade_type VARCHAR(100),
                  entry_zone VARCHAR(100),
                  stop_loss DOUBLE PRECISION,
                  target1 DOUBLE PRECISION,
                  target2 DOUBLE PRECISION,
                  target3 DOUBLE PRECISION,
                  risk_reward DOUBLE PRECISION,
                  confidence DOUBLE PRECISION,
                  invalidation_point VARCHAR(255),
                  reasoning TEXT,
                  payload TEXT,
                  created_at VARCHAR(50) DEFAULT CURRENT_TIMESTAMP,
                  updated_at VARCHAR(50) DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                  id SERIAL PRIMARY KEY,
                  event_type VARCHAR(100) NOT NULL,
                  actor VARCHAR(100),
                  symbol VARCHAR(50),
                  entity_type VARCHAR(100),
                  entity_id VARCHAR(100),
                  message TEXT,
                  payload TEXT,
                  created_at VARCHAR(50) DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tokens (
                  id SERIAL PRIMARY KEY,
                  provider VARCHAR(50) NOT NULL,
                  access_token TEXT NOT NULL,
                  refresh_token TEXT,
                  expires_at VARCHAR(50),
                  created_at VARCHAR(50) DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS signal_history (
                  id SERIAL PRIMARY KEY,
                  symbol VARCHAR(50) NOT NULL,
                  signal_type VARCHAR(50) NOT NULL,
                  score DOUBLE PRECISION,
                  payload TEXT,
                  created_at VARCHAR(50) DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS closed_trades (
                  id SERIAL PRIMARY KEY,
                  symbol VARCHAR(50) NOT NULL,
                  entry_price DOUBLE PRECISION,
                  exit_price DOUBLE PRECISION,
                  profit_loss DOUBLE PRECISION,
                  closed_at VARCHAR(50) DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS provider_status (
                  id SERIAL PRIMARY KEY,
                  provider VARCHAR(50) UNIQUE NOT NULL,
                  status VARCHAR(50) NOT NULL,
                  last_success VARCHAR(50),
                  error_message TEXT,
                  updated_at VARCHAR(50) DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS missing_symbol_log (
                  id SERIAL PRIMARY KEY,
                  symbol VARCHAR(50) NOT NULL,
                  error_message TEXT,
                  retry_count INTEGER DEFAULT 0,
                  updated_at VARCHAR(50) DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS company_symbol_registry (
                  isin VARCHAR(50) PRIMARY KEY,
                  company_name VARCHAR(255) NOT NULL,
                  company_aliases TEXT,
                  sector VARCHAR(255),
                  nse_symbol VARCHAR(50),
                  bse_symbol VARCHAR(50),
                  nse_ticker VARCHAR(50),
                  bse_ticker VARCHAR(50),
                  preferred_exchange VARCHAR(10) DEFAULT 'NSE',
                  active_quote_source VARCHAR(10) DEFAULT 'NSE',
                  fallback_reason TEXT,
                  last_verified VARCHAR(50)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS signal_records (
                  signal_id VARCHAR(100) PRIMARY KEY,
                  symbol VARCHAR(50) NOT NULL,
                  direction VARCHAR(20) NOT NULL,
                  suggested_time VARCHAR(50),
                  suggested_timestamp DOUBLE PRECISION,
                  suggested_price DOUBLE PRECISION,
                  entry_price DOUBLE PRECISION,
                  stop_loss DOUBLE PRECISION,
                  target_1 DOUBLE PRECISION,
                  target_2 DOUBLE PRECISION,
                  target_3 DOUBLE PRECISION,
                  initial_confidence DOUBLE PRECISION,
                  initial_reason TEXT,
                  current_price DOUBLE PRECISION,
                  current_pl_percent DOUBLE PRECISION,
                  max_gain_percent DOUBLE PRECISION,
                  max_loss_percent DOUBLE PRECISION,
                  max_drawdown_percent DOUBLE PRECISION,
                  time_active VARCHAR(50),
                  latest_confidence DOUBLE PRECISION,
                  status VARCHAR(50),
                  provider VARCHAR(50),
                  freshness VARCHAR(50),
                  max_price_reached DOUBLE PRECISION,
                  min_price_reached DOUBLE PRECISION,
                  initial_stop_loss DOUBLE PRECISION,
                  current_trailing_stop DOUBLE PRECISION,
                  trailing_activated_at VARCHAR(50),
                  highest_price_since_entry DOUBLE PRECISION,
                  lowest_price_since_entry DOUBLE PRECISION,
                  trailing_status VARCHAR(50),
                  outcome VARCHAR(50),
                  archived_at VARCHAR(50),
                  action_at_suggestion VARCHAR(50),
                  trailing_activated INTEGER DEFAULT 0,
                  target_hit_status VARCHAR(50),
                  stop_loss_hit_status VARCHAR(50)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS live_quotes (
                  symbol VARCHAR(50) PRIMARY KEY,
                  price DOUBLE PRECISION,
                  previous_close DOUBLE PRECISION,
                  change_pct DOUBLE PRECISION,
                  volume DOUBLE PRECISION,
                  provider VARCHAR(100),
                  market_status VARCHAR(50),
                  open DOUBLE PRECISION,
                  day_high DOUBLE PRECISION,
                  day_low DOUBLE PRECISION,
                  fifty_day_average DOUBLE PRECISION,
                  two_hundred_day_average DOUBLE PRECISION,
                  year_high DOUBLE PRECISION,
                  year_low DOUBLE PRECISION,
                  market_cap DOUBLE PRECISION,
                  pe_ratio DOUBLE PRECISION,
                  dividend_yield DOUBLE PRECISION,
                  updated_at VARCHAR(50)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scanner_snapshots (
                  id SERIAL PRIMARY KEY,
                  scan_type VARCHAR(100) NOT NULL,
                  symbol VARCHAR(50) NOT NULL,
                  score DOUBLE PRECISION,
                  grade VARCHAR(10),
                  rank INTEGER,
                  decision VARCHAR(100),
                  reason TEXT,
                  payload TEXT,
                  updated_at VARCHAR(50) NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS opportunity_rankings (
                  id SERIAL PRIMARY KEY,
                  bucket VARCHAR(100) NOT NULL,
                  symbol VARCHAR(50) NOT NULL,
                  rank INTEGER,
                  score DOUBLE PRECISION,
                  grade VARCHAR(10),
                  risk_score DOUBLE PRECISION,
                  confidence_score DOUBLE PRECISION,
                  sector VARCHAR(255),
                  payload TEXT,
                  updated_at VARCHAR(50) NOT NULL
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signal_records(symbol);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_signals_status ON signal_records(status);")
            conn.commit()
            logger.info("PostgreSQL database schemas created successfully.")
    except Exception as exc:
        conn.rollback()
        logger.error(f"Failed to migrate PostgreSQL: {exc}")
        raise
    finally:
        pool.putconn(conn)
