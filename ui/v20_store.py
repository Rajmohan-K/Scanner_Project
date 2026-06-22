from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from data.market_data_provider import get_market_data_provider
from ui.storage import list_scans, load_scan


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "ui" / "data" / "v20.sqlite"
MIGRATION_PATH = PROJECT_ROOT / "migrations" / "001_v20_schema.sql"
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
LIVE_PURGE_MARKER = PROJECT_ROOT / ".scanner_cache" / ".v20_live_purge_v3_done"
LIVE_REFRESH_SECONDS = 60
REALTIME_REFRESH_SECONDS = 1
REALTIME_STALE_SECONDS = 90
_LAST_LIVE_REFRESH: datetime | None = None
_LAST_REALTIME_REFRESH: datetime | None = None
_LAST_HOT_CACHE_REFRESH: datetime | None = None
_DB_READY = False


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def ensure_db() -> None:
    global _DB_READY
    if _DB_READY:
        return
    with connect() as conn:
        migrations_needed = True
        try:
            migrations_needed = not _core_tables_exist(conn)
        except sqlite3.OperationalError:
            migrations_needed = True
        if migrations_needed:
            migration_paths = sorted(MIGRATIONS_DIR.glob("*.sql")) or [MIGRATION_PATH]
            for migration_path in migration_paths:
                try:
                    conn.executescript(migration_path.read_text(encoding="utf-8"))
                except sqlite3.OperationalError as exc:
                    if "disk i/o error" not in str(exc).lower() or not _core_tables_exist(conn):
                        raise
        else:
            _apply_optional_migrations(conn)
        timestamp = now()
        conn.execute(
            "INSERT OR IGNORE INTO users(id, email, name, role, created_at, updated_at) VALUES(1, ?, ?, ?, ?, ?)",
            ("analyst@scanner.local", "Default Analyst", "admin", timestamp, timestamp),
        )
        conn.execute(
            "INSERT OR IGNORE INTO watchlists(id, user_id, name, created_at, updated_at) VALUES(1, 1, 'My Watchlist', ?, ?)",
            (timestamp, timestamp),
        )
        conn.execute(
            "INSERT OR IGNORE INTO portfolios(id, user_id, name, created_at, updated_at) VALUES(1, 1, 'Core Portfolio', ?, ?)",
            (timestamp, timestamp),
        )
    purge_legacy_dummy_data()
    _DB_READY = True


def _tables_exist(conn: sqlite3.Connection, required: set[str]) -> bool:
    existing = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN (%s)" % ",".join("?" for _ in required),
            tuple(required),
        ).fetchall()
    }
    return required.issubset(existing)


def _core_tables_exist(conn: sqlite3.Connection) -> bool:
    required = {
        "stocks",
        "stock_prices",
        "profitability_scores",
        "market_indices",
        "live_quotes",
        "scanner_snapshots",
        "opportunity_rankings",
    }
    return _tables_exist(conn, required)


def _enterprise_tables_exist(conn: sqlite3.Connection) -> bool:
    required = {
        "daily_candles",
        "technical_indicators",
        "scanner_results",
        "trade_plans",
        "backtest_results",
        "audit_logs",
    }
    return _tables_exist(conn, required)


def _required_tables_exist(conn: sqlite3.Connection) -> bool:
    return _core_tables_exist(conn)


def _apply_optional_migrations(conn: sqlite3.Connection) -> None:
    if _enterprise_tables_exist(conn):
        return
    migration_path = MIGRATIONS_DIR / "005_enterprise_realtime_contract.sql"
    if not migration_path.exists():
        return
    try:
        conn.executescript(migration_path.read_text(encoding="utf-8"))
    except sqlite3.OperationalError as exc:
        if "disk i/o error" not in str(exc).lower():
            raise


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _maybe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rating(score: float) -> str:
    if score >= 90:
        return "Strong Buy"
    if score >= 78:
        return "Buy"
    if score >= 65:
        return "Watch"
    if score >= 50:
        return "Hold"
    return "Avoid"


def purge_legacy_dummy_data() -> None:
    if LIVE_PURGE_MARKER.exists():
        return
    with connect() as conn:
        for table in (
            "watchlist_items",
            "portfolio_holdings",
            "alerts",
            "paper_trades",
            "ai_recommendations",
            "profitability_scores",
            "financial_metrics",
            "stock_prices",
            "stocks",
            "market_indices",
            "news_articles",
        ):
            conn.execute(f"DELETE FROM {table}")
    LIVE_PURGE_MARKER.parent.mkdir(parents=True, exist_ok=True)
    LIVE_PURGE_MARKER.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")


def user_data_cutoff() -> str:
    if LIVE_PURGE_MARKER.exists():
        return LIVE_PURGE_MARKER.read_text(encoding="utf-8").strip()
    return datetime.now().isoformat(timespec="seconds")


def _scan_time_from_id(scan_id: str) -> str:
    try:
        return datetime.strptime(scan_id, "%Y%m%d_%H%M%S").isoformat(timespec="seconds")
    except Exception:
        return ""


def _score_from_row(row: dict[str, Any]) -> dict[str, float | str]:
    revenue_growth = _maybe_float(row.get("revenue_growth"))
    eps_growth = _maybe_float(row.get("eps_growth"))
    roe = _maybe_float(row.get("roe"))
    roce = _maybe_float(row.get("roce"))
    debt = _maybe_float(row.get("debt_to_equity")) or _maybe_float(row.get("debt_ratio"))
    pe = _maybe_float(row.get("pe_ratio")) or _maybe_float(row.get("pe"))
    momentum = _maybe_float(row.get("momentum_score")) or _maybe_float(row.get("ml_probability"))
    profitability = _maybe_float(row.get("profitability_score")) or _maybe_float(row.get("ml_probability"))
    quality = _maybe_float(row.get("quality_score")) or _maybe_float(row.get("data_reliability_score"))
    risk = _maybe_float(row.get("risk_score"))
    provided = [revenue_growth, eps_growth, roe, roce, debt, pe, momentum, profitability, quality, risk]
    if profitability is None and sum(value is not None for value in provided) < 5:
        raise ValueError("insufficient real scoring inputs")
    revenue_growth = revenue_growth if revenue_growth is not None else 0.0
    eps_growth = eps_growth if eps_growth is not None else 0.0
    roe = roe if roe is not None else 0.0
    roce = roce if roce is not None else roe
    debt = debt if debt is not None else 0.0
    pe = pe if pe is not None else 0.0
    momentum = momentum if momentum is not None else profitability or 0.0
    profitability = profitability if profitability is not None else (max(revenue_growth, 0) + max(eps_growth, 0) + max(roe, 0)) / 3
    quality = quality if quality is not None else max(0, min(100, (roe + roce) / 2))
    risk = risk if risk is not None else max(0, min(100, debt * 20 + max(pe - 30, 0)))
    value = max(0, min(100, 85 - max(pe - 12, 0) * 1.7 - debt * 12))
    growth = max(0, min(100, revenue_growth * 1.7 + eps_growth * 1.3 + roe))
    final = max(
        0,
        min(
            100,
            profitability * 0.26
            + growth * 0.18
            + value * 0.14
            + momentum * 0.18
            + quality * 0.14
            + max(0, 100 - risk) * 0.10,
        ),
    )
    explanation = (
        f"{_rating(final)} because profitability {profitability:.0f}, growth {growth:.0f}, "
        f"value {value:.0f}, momentum {momentum:.0f}, quality {quality:.0f}, risk {risk:.0f}."
    )
    return {
        "revenue_growth": revenue_growth,
        "eps_growth": eps_growth,
        "roe": roe,
        "roce": roce,
        "debt_ratio": debt,
        "pe": pe,
        "peg": _as_float(row.get("peg_ratio"), max(pe / max(eps_growth, 1), 0)),
        "roa": _as_float(row.get("roa"), max(roe * 0.55, 0)),
        "dividend_yield": _as_float(row.get("dividend_yield"), 0),
        "net_profit_margin": _as_float(row.get("net_profit_margin"), max(roe * 0.8, 0)),
        "free_cash_flow": _as_float(row.get("free_cash_flow"), max(revenue_growth, 0) * 1000000),
        "profitability": max(0, min(100, profitability)),
        "growth": growth,
        "value": value,
        "momentum": max(0, min(100, momentum)),
        "risk": max(0, min(100, risk)),
        "quality": max(0, min(100, quality)),
        "final": round(final, 2),
        "explanation": explanation,
        "rating": _rating(final),
    }


def _scanner_rows_from_db(limit: int = 500, family: str | None = None) -> list[dict[str, Any]]:
    try:
        with connect() as conn:
            if not _tables_exist(conn, {"scanner_results"}):
                return []
            clauses = ["payload IS NOT NULL", "payload != ''"]
            params: list[Any] = []
            if family:
                family_like = f"%{family.replace('-', '_')}%"
                alt_like = f"%{family.replace('_', '-')}%"
                clauses.append(
                    "(scan_family LIKE ? OR scanner_bucket LIKE ? OR pipeline_stage LIKE ? OR scan_type LIKE ? "
                    "OR scan_family LIKE ? OR scanner_bucket LIKE ? OR pipeline_stage LIKE ? OR scan_type LIKE ?)"
                )
                params.extend([family_like, family_like, family_like, family_like, alt_like, alt_like, alt_like, alt_like])
            params.append(max(1, min(int(limit or 500), 2000)))
            query = f"""
                SELECT scanner_run_id, scan_type, scan_family, scanner_bucket, pipeline_stage,
                       result_bucket, result_role, symbol, rank, payload, updated_at
                FROM scanner_results
                WHERE {' AND '.join(clauses)}
                ORDER BY updated_at DESC, scanner_run_id DESC, rank ASC, id ASC
                LIMIT ?
            """
            rows = conn.execute(query, tuple(params)).fetchall()
    except sqlite3.Error:
        return []
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        try:
            payload = json.loads(str(row["payload"] or "{}"))
        except json.JSONDecodeError:
            payload = {}
        symbol = str(payload.get("symbol") or payload.get("stock") or row["symbol"] or "").strip().upper()
        if not symbol:
            continue
        dedupe_key = (str(row["scanner_run_id"] or ""), str(row["result_bucket"] or ""), symbol)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        output.append(
            {
                **payload,
                "symbol": symbol,
                "stock": payload.get("stock") or symbol,
                "scan_id": row["scanner_run_id"],
                "scan_type": row["scan_type"],
                "scan_family": row["scan_family"],
                "scanner_bucket": row["scanner_bucket"],
                "pipeline_stage": row["pipeline_stage"],
                "result_bucket": row["result_bucket"],
                "result_role": row["result_role"],
                "rank": row["rank"],
                "updated_at": row["updated_at"],
            }
        )
    return output


def _stock_rows_from_scans() -> list[dict[str, Any]]:
    db_rows = _scanner_rows_from_db(limit=500)
    if db_rows:
        return db_rows
    rows: list[dict[str, Any]] = []
    cutoff = user_data_cutoff()
    for summary in list_scans(limit=20):
        scan_id = str(summary.get("scan_id") or summary.get("id") or "")
        scan_time = str(summary.get("created_at") or summary.get("updated_at") or summary.get("completed_at") or _scan_time_from_id(scan_id) or "")
        if scan_time and scan_time < cutoff:
            continue
        payload = load_scan(scan_id)
        if not payload:
            continue
        payload_time = str(payload.get("created_at") or payload.get("updated_at") or payload.get("completed_at") or _scan_time_from_id(scan_id) or "")
        if payload_time and payload_time < cutoff:
            continue
        for key in ("final_top_10", "top_25", "filtered_150", "ranked", "results"):
            values = payload.get(key)
            if isinstance(values, list):
                rows.extend([item for item in values if isinstance(item, dict)])
        if rows:
            break
    return rows


def ingest_latest_scan() -> None:
    rows = _stock_rows_from_scans()
    if not rows:
        return
    provider = get_market_data_provider()
    timestamp = now()
    with connect() as conn:
        for row in rows:
            symbol = str(row.get("symbol") or row.get("stock") or "").upper()
            if not symbol:
                continue
            live_quote = provider.get_quote(symbol)
            live_metrics = provider.get_financial_metrics(symbol)
            name = str(live_metrics.get("name") or row.get("name") or row.get("company_name") or symbol)
            sector = str(live_metrics.get("sector") or row.get("sector") or "Unclassified")
            industry = str(live_metrics.get("industry") or row.get("industry") or sector)
            market_cap = _as_float(live_metrics.get("market_cap"), _as_float(row.get("market_cap"), _as_float(row.get("market_cap_cr"), 0)))
            conn.execute(
                """
                INSERT INTO stocks(symbol, name, sector, industry, market_cap, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                  name=excluded.name, sector=excluded.sector, industry=excluded.industry,
                  market_cap=excluded.market_cap, updated_at=excluded.updated_at
                """,
                (symbol, name, sector, industry, market_cap, timestamp, timestamp),
            )
            stock_id = conn.execute("SELECT id FROM stocks WHERE symbol=?", (symbol,)).fetchone()["id"]
            price = _as_float(live_quote.get("current_price"), _as_float(row.get("live_price"), _as_float(row.get("current_price"), _as_float(row.get("last_close"), 0))))
            previous = _as_float(live_quote.get("previous_close"), 0)
            change = ((price - previous) / previous * 100) if price and previous else _as_float(row.get("change"), _as_float(row.get("change_pct"), 0))
            volume = _as_float(live_quote.get("volume"), _as_float(row.get("volume"), 0))
            if price > 0:
                conn.execute(
                    "INSERT INTO stock_prices(stock_id, price, change_pct, volume, price_date, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?)",
                    (stock_id, price, change, volume, timestamp[:10], timestamp, timestamp),
                )
            scoring_row = {**row, **{key: value for key, value in live_metrics.items() if value not in (None, "")}}
            try:
                score = _score_from_row(scoring_row)
            except ValueError:
                continue
            conn.execute(
                """
                INSERT INTO financial_metrics(stock_id, pe, peg, roe, roa, roce, debt_ratio, dividend_yield,
                  revenue_growth, eps_growth, net_profit_margin, free_cash_flow, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(stock_id) DO UPDATE SET
                  pe=excluded.pe, peg=excluded.peg, roe=excluded.roe, roa=excluded.roa, roce=excluded.roce,
                  debt_ratio=excluded.debt_ratio, dividend_yield=excluded.dividend_yield,
                  revenue_growth=excluded.revenue_growth, eps_growth=excluded.eps_growth,
                  net_profit_margin=excluded.net_profit_margin, free_cash_flow=excluded.free_cash_flow,
                  updated_at=excluded.updated_at
                """,
                (
                    stock_id,
                    score["pe"],
                    score["peg"],
                    score["roe"],
                    score["roa"],
                    score["roce"],
                    score["debt_ratio"],
                    score["dividend_yield"],
                    score["revenue_growth"],
                    score["eps_growth"],
                    score["net_profit_margin"],
                    score["free_cash_flow"],
                    timestamp,
                    timestamp,
                ),
            )
            conn.execute(
                """
                INSERT INTO profitability_scores(stock_id, profitability_score, growth_score, value_score,
                  momentum_score, risk_score, quality_score, final_ai_score, explanation, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(stock_id) DO UPDATE SET
                  profitability_score=excluded.profitability_score, growth_score=excluded.growth_score,
                  value_score=excluded.value_score, momentum_score=excluded.momentum_score,
                  risk_score=excluded.risk_score, quality_score=excluded.quality_score,
                  final_ai_score=excluded.final_ai_score, explanation=excluded.explanation,
                  updated_at=excluded.updated_at
                """,
                (
                    stock_id,
                    score["profitability"],
                    score["growth"],
                    score["value"],
                    score["momentum"],
                    score["risk"],
                    score["quality"],
                    score["final"],
                    score["explanation"],
                    timestamp,
                    timestamp,
                ),
            )
            conn.execute(
                "DELETE FROM ai_recommendations WHERE stock_id=?",
                (stock_id,),
            )
            conn.execute(
                """
                INSERT INTO ai_recommendations(stock_id, rating, confidence, reasoning, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (stock_id, score["rating"], score["final"], score["explanation"], timestamp, timestamp),
            )


def refresh_supporting_live_data() -> None:
    timestamp = now()
    provider = get_market_data_provider()
    with connect() as conn:
        conn.execute("DELETE FROM market_indices")
        for item in provider.get_indices():
            conn.execute(
                """
                INSERT INTO market_indices(symbol, name, value, change_pct, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET value=excluded.value, change_pct=excluded.change_pct, updated_at=excluded.updated_at
                """,
                (
                    item.get("symbol"),
                    item.get("name") or item.get("symbol"),
                    _as_float(item.get("value")),
                    _as_float(item.get("change_pct")),
                    timestamp,
                    timestamp,
                ),
            )
        conn.execute("DELETE FROM news_articles WHERE stock_id IS NULL")
        for article in provider.get_news(limit=20):
            conn.execute(
                """
                INSERT INTO news_articles(title, category, source, url, published_at, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article.get("title"),
                    article.get("category") or "Market",
                    article.get("source") or "provider",
                    article.get("url") or "",
                    article.get("published_at") or timestamp,
                    timestamp,
                    timestamp,
                ),
            )


def refresh_realtime_snapshot(force: bool = False, stock_limit: int = 0) -> None:
    global _LAST_REALTIME_REFRESH
    current = datetime.now()
    if not force and _LAST_REALTIME_REFRESH and (current - _LAST_REALTIME_REFRESH).total_seconds() < REALTIME_REFRESH_SECONDS:
        return
    ensure_db()
    timestamp = now()
    provider = get_market_data_provider()
    try:
        with connect() as conn:
            conn.execute("DELETE FROM market_indices")
            for item in provider.get_indices():
                conn.execute(
                    """
                    INSERT INTO market_indices(symbol, name, value, change_pct, created_at, updated_at)
                    VALUES(?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol) DO UPDATE SET value=excluded.value, change_pct=excluded.change_pct, updated_at=excluded.updated_at
                    """,
                    (
                        item.get("symbol"),
                        item.get("name") or item.get("symbol"),
                        _as_float(item.get("value")),
                        _as_float(item.get("change_pct")),
                        timestamp,
                        timestamp,
                    ),
                )
            if stock_limit > 0:
                stock_rows = conn.execute(
                    """
                    SELECT s.id, s.symbol
                    FROM stocks s
                    JOIN profitability_scores ps ON ps.stock_id = s.id
                    ORDER BY ps.final_ai_score DESC
                    LIMIT ?
                    """,
                    (stock_limit,),
                ).fetchall()
                for stock in stock_rows:
                    quote = provider.get_quote(stock["symbol"], use_cache=False)
                    price = _as_float(quote.get("current_price"), 0)
                    if price <= 0:
                        continue
                    previous = _as_float(quote.get("previous_close"), 0)
                    change = ((price - previous) / previous * 100) if previous else 0
                    volume = _as_float(quote.get("volume"), 0)
                    conn.execute(
                        "INSERT INTO stock_prices(stock_id, price, change_pct, volume, price_date, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?)",
                        (stock["id"], price, change, volume, timestamp[:10], timestamp, timestamp),
                    )
    except sqlite3.Error:
        _LAST_REALTIME_REFRESH = current
        return
    _LAST_REALTIME_REFRESH = current


def refresh_live_store(force: bool = False) -> None:
    global _LAST_LIVE_REFRESH
    if not force and _LAST_LIVE_REFRESH and (datetime.now() - _LAST_LIVE_REFRESH).total_seconds() < LIVE_REFRESH_SECONDS:
        return
    clear_analytics_universe()
    ingest_latest_scan()
    refresh_supporting_live_data()
    _LAST_LIVE_REFRESH = datetime.now()


def clear_analytics_universe() -> None:
    with connect() as conn:
        for table in ("ai_recommendations", "profitability_scores", "financial_metrics", "stock_prices", "stocks"):
            conn.execute(f"DELETE FROM {table}")


def rows(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    ensure_db()
    with connect() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def execute(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    ensure_db()
    with connect() as conn:
        cursor = conn.execute(query, params)
        return {"lastrowid": cursor.lastrowid, "rowcount": cursor.rowcount}


def stock_query(filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    ensure_db()
    filters = filters or {}
    clauses = []
    params: list[Any] = []
    search = str(filters.get("search") or "").strip()
    if search:
        clauses.append("(s.symbol LIKE ? OR s.name LIKE ? OR s.sector LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like])
    for key, column in {
        "sector": "s.sector",
        "rating": "ar.rating",
    }.items():
        value = filters.get(key)
        if value:
            clauses.append(f"{column} = ?")
            params.append(value)
    numeric_filters = {
        "min_profitability": "ps.profitability_score >= ?",
        "min_ai_score": "ps.final_ai_score >= ?",
        "max_risk": "ps.risk_score <= ?",
        "min_roe": "fm.roe >= ?",
        "max_pe": "fm.pe <= ?",
    }
    for key, clause in numeric_filters.items():
        value = filters.get(key)
        if value not in (None, ""):
            clauses.append(clause)
            params.append(_as_float(value))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sort = str(filters.get("sort") or "ps.final_ai_score")
    allowed_sort = {
        "symbol": "s.symbol",
        "price": "latest.price",
        "market_cap": "s.market_cap",
        "profitability_score": "ps.profitability_score",
        "ai_score": "ps.final_ai_score",
        "pe": "fm.pe",
        "roe": "fm.roe",
        "eps_growth": "fm.eps_growth",
    }
    sort_sql = allowed_sort.get(sort, "ps.final_ai_score")
    direction = "ASC" if str(filters.get("direction")).lower() == "asc" else "DESC"
    limit = max(1, min(int(filters.get("limit", 50) or 50), 500))
    offset = max(0, int(filters.get("offset", 0) or 0))
    sql = f"""
        SELECT
          s.symbol, s.name, s.sector, s.industry, s.market_cap,
          latest.price AS live_price, latest.change_pct AS change_pct, latest.volume,
          fm.pe, fm.peg, fm.roe, fm.roa, fm.roce, fm.debt_ratio, fm.dividend_yield,
          fm.revenue_growth, fm.eps_growth, fm.net_profit_margin, fm.free_cash_flow,
          ps.profitability_score, ps.growth_score, ps.value_score, ps.momentum_score,
          ps.risk_score, ps.quality_score, ps.final_ai_score, ps.explanation,
          ar.rating AS ai_rating, ar.confidence AS ai_confidence, ar.reasoning
        FROM stocks s
        JOIN financial_metrics fm ON fm.stock_id = s.id
        JOIN profitability_scores ps ON ps.stock_id = s.id
        JOIN (
          SELECT sp1.*
          FROM stock_prices sp1
          JOIN (
            SELECT stock_id, MAX(id) AS max_id FROM stock_prices GROUP BY stock_id
          ) latest_ids ON latest_ids.max_id = sp1.id
        ) latest ON latest.stock_id = s.id
        JOIN (
          SELECT ar1.*
          FROM ai_recommendations ar1
          JOIN (
            SELECT stock_id, MAX(id) AS max_id FROM ai_recommendations GROUP BY stock_id
          ) latest_ar ON latest_ar.max_id = ar1.id
        ) ar ON ar.stock_id = s.id
        {where}
        ORDER BY {sort_sql} {direction}
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    with connect() as conn:
        return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]


def _scan_result_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for key in ("final_top_10", "ranked", "top_25", "filtered_150", "results", "all_results"):
        value = payload.get(key)
        if not isinstance(value, list):
            continue
        for row in value:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or row.get("stock") or "").strip().upper()
            if not symbol:
                continue
            dedupe_key = (symbol, key)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            rows.append(row)
    return rows


def _row_horizon(row: dict[str, Any], payload: dict[str, Any]) -> str | None:
    text = " ".join(
        str(value or "")
        for value in (
            row.get("scan_family"),
            row.get("scanner_bucket"),
            row.get("pipeline_stage"),
            row.get("scan_mode"),
            row.get("best_horizon"),
            row.get("tag"),
            row.get("category"),
            payload.get("scan_family"),
            payload.get("scanner_bucket"),
            payload.get("pipeline_stage"),
            payload.get("scan_mode"),
        )
    ).lower().replace("-", "_")
    if any(token in text for token in ("intraday", "premarket", "open_confirmation", "market_open", "groww")):
        return "intraday"
    if "swing" in text:
        return "swing"
    if any(token in text for token in ("long_term", "longterm", "value", "dividend", "investment", "quality")):
        return "longterm"
    return None


def _row_is_trade_available(row: dict[str, Any]) -> bool:
    action = str(
        row.get("final_decision")
        or row.get("action")
        or row.get("ai_rating")
        or row.get("recommendation")
        or row.get("premarket_action")
        or row.get("signal")
        or row.get("trade_type")
        or ""
    ).upper()
    if any(token in action for token in ("AVOID", "REJECT", "NO TRADE", "HOLD")):
        return False
    if any(token in action for token in ("TRADE", "BUY", "LONG", "STRONG")):
        return True
    score = max(
        _as_float(row.get("meta_score")),
        _as_float(row.get("final_ai_score")),
        _as_float(row.get("profitability_score")),
        _as_float(row.get("ml_probability")),
        _as_float(row.get("confidence_pct")),
    )
    risk = _as_float(row.get("risk_score"), 50)
    return score >= 65 and risk <= 65


def _trade_availability_from_scans(stocks: list[dict[str, Any]]) -> dict[str, Any]:
    buckets = {
        "intraday": {"symbols": set(), "latest_scan_id": "", "latest_updated": ""},
        "swing": {"symbols": set(), "latest_scan_id": "", "latest_updated": ""},
        "longterm": {"symbols": set(), "latest_scan_id": "", "latest_updated": ""},
    }
    db_rows = _scanner_rows_from_db(limit=2000)
    if db_rows:
        for row in db_rows:
            horizon = _row_horizon(row, row)
            if not horizon or horizon not in buckets or not _row_is_trade_available(row):
                continue
            symbol = str(row.get("symbol") or row.get("stock") or "").strip().upper()
            if not symbol:
                continue
            buckets[horizon]["symbols"].add(symbol)
            updated_at = str(row.get("updated_at") or "")
            if updated_at > str(buckets[horizon]["latest_updated"]):
                buckets[horizon]["latest_updated"] = updated_at
                buckets[horizon]["latest_scan_id"] = str(row.get("scan_id") or "")
    else:
        for summary in list_scans(limit=120):
            payload = load_scan(summary.get("scan_id", ""))
            if not payload:
                continue
            scan_id = str(payload.get("scan_id") or summary.get("scan_id") or "")
            created_at = str(payload.get("created_at") or summary.get("created_at") or "")
            for row in _scan_result_rows(payload):
                horizon = _row_horizon(row, payload)
                if not horizon or horizon not in buckets or not _row_is_trade_available(row):
                    continue
                symbol = str(row.get("symbol") or row.get("stock") or "").strip().upper()
                if not symbol:
                    continue
                buckets[horizon]["symbols"].add(symbol)
                if created_at > str(buckets[horizon]["latest_updated"]):
                    buckets[horizon]["latest_updated"] = created_at
                    buckets[horizon]["latest_scan_id"] = scan_id

    if stocks:
        for row in stocks:
            if not _row_is_trade_available(row):
                continue
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            if _as_float(row.get("momentum_score")) >= 65 or _as_float(row.get("change_pct")) > 0:
                buckets["intraday"]["symbols"].add(symbol)
            if _as_float(row.get("growth_score")) >= 65 or _as_float(row.get("quality_score")) >= 65:
                buckets["swing"]["symbols"].add(symbol)
            if _as_float(row.get("value_score")) >= 65 or _as_float(row.get("profitability_score")) >= 70:
                buckets["longterm"]["symbols"].add(symbol)

    return {
        key: {
            "count": len(value["symbols"]),
            "symbols": sorted(value["symbols"])[:50],
            "latest_scan_id": value["latest_scan_id"],
            "latest_updated": value["latest_updated"],
        }
        for key, value in buckets.items()
    }


def _market_sentiment_payload(
    stocks: list[dict[str, Any]],
    indices: list[dict[str, Any]],
    sector_heatmap: list[dict[str, Any]],
    avg_profitability: float,
    avg_risk: float,
    strong_buy_count: int,
    advances: int,
    declines: int,
) -> dict[str, Any]:
    total = max(len(stocks), 1)
    advance_pct = (advances / total) * 100
    avg_index_change = (
        sum(_as_float(item.get("change_pct")) for item in indices) / len(indices)
        if indices
        else 0.0
    )
    index_score = max(0.0, min(100.0, 50 + avg_index_change * 12))
    sector_score = (
        sum(1 for item in sector_heatmap if _as_float(item.get("profit")) >= 0) / max(len(sector_heatmap), 1)
    ) * 100
    strong_buy_score = (strong_buy_count / total) * 100
    risk_score = max(0.0, min(100.0, 100 - avg_risk))
    score = round(
        advance_pct * 0.28
        + index_score * 0.22
        + sector_score * 0.18
        + avg_profitability * 0.17
        + strong_buy_score * 0.08
        + risk_score * 0.07,
        2,
    )
    if score >= 75:
        label = "Strong Bullish"
    elif score >= 58:
        label = "Bullish"
    elif score <= 35:
        label = "Bearish"
    else:
        label = "Neutral"
    return {
        "label": label,
        "score": score,
        "source": "live breadth, live indices, sector heatmap, profitability, strong-buy ratio, risk",
        "components": {
            "advance_pct": round(advance_pct, 2),
            "avg_index_change_pct": round(avg_index_change, 2),
            "index_score": round(index_score, 2),
            "sector_score": round(sector_score, 2),
            "avg_profitability": round(avg_profitability, 2),
            "strong_buy_score": round(strong_buy_score, 2),
            "risk_adjusted_score": round(risk_score, 2),
        },
    }


def _score_from_row(row: dict[str, Any]) -> float:
    return max(
        _as_float(row.get("final_ai_score")),
        _as_float(row.get("profitability_score")),
        _as_float(row.get("ml_probability")),
        _as_float(row.get("confidence_pct")),
        _as_float(row.get("momentum_score")),
    )


def _row_grade(row: dict[str, Any]) -> str:
    rating = str(row.get("ai_rating") or row.get("rating") or row.get("final_decision") or "").strip()
    if rating:
        return rating
    score = _score_from_row(row)
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    return "Reject"


def _snapshot_row(row: dict[str, Any]) -> dict[str, Any]:
    symbol = str(row.get("symbol") or row.get("stock") or "").strip().upper()
    return {
        "symbol": symbol,
        "name": row.get("name") or symbol,
        "sector": row.get("sector") or "Unknown",
        "industry": row.get("industry") or "",
        "ltp": round(_as_float(row.get("live_price") or row.get("ltp") or row.get("price")), 2),
        "change_pct": round(_as_float(row.get("change_pct")), 2),
        "volume": _as_float(row.get("volume")),
        "score": round(_score_from_row(row), 2),
        "profitability_score": round(_as_float(row.get("profitability_score")), 2),
        "growth_score": round(_as_float(row.get("growth_score")), 2),
        "value_score": round(_as_float(row.get("value_score")), 2),
        "momentum_score": round(_as_float(row.get("momentum_score")), 2),
        "risk_score": round(_as_float(row.get("risk_score")), 2),
        "quality_score": round(_as_float(row.get("quality_score")), 2),
        "confidence_score": round(_as_float(row.get("ai_confidence")), 2),
        "grade": _row_grade(row),
        "decision": row.get("ai_rating") or row.get("final_decision") or row.get("signal") or "Watch",
        "reason": row.get("reasoning") or row.get("explanation") or "",
        "entry": row.get("entry") or row.get("entry_price") or row.get("live_price"),
        "stop_loss": row.get("stop_loss") or row.get("stoploss"),
        "target": row.get("target") or row.get("target1"),
        "updated_at": row.get("updated_at") or now(),
    }


def _ranked_bucket(rows_in: list[dict[str, Any]], key_fn, limit: int, require_tradeable: bool = True) -> list[dict[str, Any]]:
    candidates = [row for row in rows_in if str(row.get("symbol") or "").strip()]
    if require_tradeable:
        candidates = [row for row in candidates if _row_is_trade_available(row)]
    ranked = sorted(candidates, key=key_fn, reverse=True)[:limit]
    output = []
    for index, row in enumerate(ranked, 1):
        item = _snapshot_row(row)
        item["rank"] = index
        output.append(item)
    return output


def _opportunity_buckets_from_stocks(stocks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "intraday_top_10": _ranked_bucket(
            stocks,
            lambda row: (
                _as_float(row.get("momentum_score")) * 0.45
                + max(_as_float(row.get("change_pct")), 0) * 6
                + min(_as_float(row.get("volume")) / 1000000, 30) * 0.35
                + _score_from_row(row) * 0.25
                - _as_float(row.get("risk_score")) * 0.2
            ),
            10,
        ),
        "intraday_watch_25": _ranked_bucket(
            stocks,
            lambda row: _as_float(row.get("momentum_score")) * 0.55 + _score_from_row(row) * 0.35 - _as_float(row.get("risk_score")) * 0.2,
            25,
        ),
        "premarket_top_10": _ranked_bucket(
            stocks,
            lambda row: max(_as_float(row.get("change_pct")), 0) * 12 + _as_float(row.get("momentum_score")) * 0.45 + _score_from_row(row) * 0.25,
            10,
        ),
        "open_confirmation_top_10": _ranked_bucket(
            stocks,
            lambda row: _as_float(row.get("quality_score")) * 0.35 + _as_float(row.get("momentum_score")) * 0.35 + max(_as_float(row.get("change_pct")), 0) * 8,
            10,
        ),
        "swing_top_20": _ranked_bucket(
            stocks,
            lambda row: _as_float(row.get("growth_score")) * 0.35 + _as_float(row.get("quality_score")) * 0.35 + _score_from_row(row) * 0.25 - _as_float(row.get("risk_score")) * 0.2,
            20,
        ),
        "breakouts_top_10": _ranked_bucket(
            stocks,
            lambda row: _as_float(row.get("momentum_score")) * 0.6 + max(_as_float(row.get("change_pct")), 0) * 10,
            10,
        ),
        "momentum_top_10": _ranked_bucket(stocks, lambda row: _as_float(row.get("momentum_score")) * 0.75 + _score_from_row(row) * 0.2, 10),
        "high_volume_top_10": _ranked_bucket(
            [row for row in stocks if _as_float(row.get("volume")) > 0],
            lambda row: _as_float(row.get("volume")),
            10,
            require_tradeable=False,
        ),
        "risk_alerts_top_10": _ranked_bucket(
            [row for row in stocks if _as_float(row.get("risk_score")) >= 65],
            lambda row: _as_float(row.get("risk_score")),
            10,
            require_tradeable=False,
        ),
    }


def store_realtime_snapshots(
    stocks: list[dict[str, Any]],
    indices: list[dict[str, Any]],
    ai_insights: list[dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    global _LAST_HOT_CACHE_REFRESH
    timestamp = now()
    buckets = _opportunity_buckets_from_stocks(stocks)
    if _LAST_HOT_CACHE_REFRESH and (datetime.now() - _LAST_HOT_CACHE_REFRESH).total_seconds() < 0.8:
        return buckets
    with connect() as conn:
        for row in stocks:
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            conn.execute(
                """
                INSERT INTO live_quotes(symbol, price, previous_close, change_pct, volume, provider, market_status, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET price=excluded.price, previous_close=excluded.previous_close,
                  change_pct=excluded.change_pct, volume=excluded.volume, provider=excluded.provider,
                  market_status=excluded.market_status, updated_at=excluded.updated_at
                """,
                (
                    symbol,
                    _as_float(row.get("live_price")),
                    None,
                    _as_float(row.get("change_pct")),
                    _as_float(row.get("volume")),
                    "configured-provider",
                    "tracked",
                    timestamp,
                ),
            )
        for row in indices:
            symbol = str(row.get("symbol") or row.get("name") or "").strip().upper()
            if not symbol:
                continue
            conn.execute(
                """
                INSERT INTO live_quotes(symbol, price, previous_close, change_pct, volume, provider, market_status, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET price=excluded.price, change_pct=excluded.change_pct,
                  provider=excluded.provider, market_status=excluded.market_status, updated_at=excluded.updated_at
                """,
                (symbol, _as_float(row.get("value")), None, _as_float(row.get("change_pct")), None, "configured-provider", "index", timestamp),
            )

        conn.execute("DELETE FROM scanner_snapshots")
        conn.execute("DELETE FROM opportunity_rankings")
        for bucket, bucket_rows in buckets.items():
            for item in bucket_rows:
                payload = json.dumps(item, default=str)
                conn.execute(
                    """
                    INSERT INTO scanner_snapshots(scan_type, symbol, score, grade, rank, decision, reason, payload, updated_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (bucket, item["symbol"], item["score"], item["grade"], item["rank"], item["decision"], item["reason"], payload, timestamp),
                )
                conn.execute(
                    """
                    INSERT INTO opportunity_rankings(bucket, symbol, rank, score, grade, risk_score, confidence_score, sector, payload, updated_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        bucket,
                        item["symbol"],
                        item["rank"],
                        item["score"],
                        item["grade"],
                        item["risk_score"],
                        item["confidence_score"],
                        item["sector"],
                        payload,
                        timestamp,
                    ),
                )
        if ai_insights is not None:
            conn.execute("DELETE FROM ai_insight_snapshots")
            for insight in ai_insights:
                payload = json.dumps(insight, default=str)
                conn.execute(
                    """
                    INSERT INTO ai_insight_snapshots(symbol, insight_type, title, rating, confidence_score, reason, payload, updated_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        insight.get("symbol"),
                        insight.get("title") or "AI Insight",
                        insight.get("title"),
                        insight.get("rating"),
                        _as_float(insight.get("confidence_score")),
                        insight.get("reason"),
                        payload,
                        timestamp,
                    ),
                )
    _LAST_HOT_CACHE_REFRESH = datetime.now()
    return buckets


def _latest_snapshot_time() -> str:
    for query in (
        "SELECT MAX(updated_at) AS updated_at FROM opportunity_rankings",
        "SELECT MAX(updated_at) AS updated_at FROM live_quotes",
        "SELECT MAX(updated_at) AS updated_at FROM scanner_snapshots",
    ):
        result = rows(query)
        value = result[0].get("updated_at") if result else None
        if value:
            return str(value)
    return ""


def _freshness(updated_at: str) -> dict[str, Any]:
    if not updated_at:
        return {"updated_at": "", "age_seconds": None, "stale": True}
    try:
        age_seconds = max(0, int((datetime.now() - datetime.fromisoformat(updated_at)).total_seconds()))
    except ValueError:
        age_seconds = None
    return {
        "updated_at": updated_at,
        "age_seconds": age_seconds,
        "stale": age_seconds is None or age_seconds > REALTIME_STALE_SECONDS,
    }


def _bucket_rows_from_db() -> dict[str, list[dict[str, Any]]]:
    bucket_names = (
        "intraday_top_10",
        "intraday_watch_25",
        "premarket_top_10",
        "open_confirmation_top_10",
        "swing_top_20",
        "breakouts_top_10",
        "momentum_top_10",
        "high_volume_top_10",
        "risk_alerts_top_10",
    )
    output: dict[str, list[dict[str, Any]]] = {name: [] for name in bucket_names}
    for row in rows("SELECT bucket, payload FROM opportunity_rankings ORDER BY bucket, rank ASC"):
        bucket = str(row.get("bucket") or "")
        if bucket not in output:
            continue
        try:
            output[bucket].append(json.loads(str(row.get("payload") or "{}")))
        except json.JSONDecodeError:
            continue
    return output


def realtime_payload() -> dict[str, Any]:
    global _LAST_HOT_CACHE_REFRESH
    ensure_db()
    refresh_realtime_snapshot()
    stocks = stock_query({"limit": 150})
    indices = rows("SELECT symbol, name, value, change_pct, updated_at FROM market_indices ORDER BY id")
    ai_insights: list[dict[str, Any]] = []
    if stocks:
        ai_insights = [
            {"title": "Top AI Pick", "symbol": stocks[0]["symbol"], "rating": stocks[0]["ai_rating"], "reason": stocks[0]["reasoning"]},
            {
                "title": "Momentum Leader",
                "symbol": max(stocks, key=lambda item: item["momentum_score"])["symbol"],
                "rating": max(stocks, key=lambda item: item["momentum_score"])["ai_rating"],
                "reason": max(stocks, key=lambda item: item["momentum_score"])["reasoning"],
            },
        ]
        store_realtime_snapshots(stocks, indices, ai_insights)
        _LAST_HOT_CACHE_REFRESH = datetime.now()

    bucket_rows = _bucket_rows_from_db()
    updated_at = _latest_snapshot_time()
    freshness = _freshness(updated_at)
    status = "live" if stocks and not freshness["stale"] else "stale" if updated_at else "empty"
    return {
        "status": status,
        "generated_at": now(),
        "freshness": freshness,
        "connection": {
            "stream": "polling",
            "websocket": False,
            "redis": False,
            "hot_cache": "sqlite+memory",
            "last_cache_refresh": _LAST_HOT_CACHE_REFRESH.isoformat(timespec="seconds") if _LAST_HOT_CACHE_REFRESH else "",
        },
        "indices": indices,
        "buckets": bucket_rows,
        "ai_insights": ai_insights or [
            json.loads(row["payload"])
            for row in rows("SELECT payload FROM ai_insight_snapshots ORDER BY updated_at DESC LIMIT 10")
            if row.get("payload")
        ],
        "events": [],
    }


def dashboard_payload() -> dict[str, Any]:
    ensure_db()
    stocks = stock_query({"limit": 100})
    indices = rows("SELECT symbol, name, value, change_pct, updated_at FROM market_indices ORDER BY id")
    news = rows("SELECT title, category, source, published_at FROM news_articles ORDER BY published_at DESC LIMIT 5")
    if not stocks:
        trade_availability = _trade_availability_from_scans([])
        realtime = realtime_payload() if rows("SELECT 1 FROM opportunity_rankings LIMIT 1") else {
            "status": "empty",
            "generated_at": now(),
            "freshness": {"updated_at": "", "age_seconds": None, "stale": True},
            "connection": {"stream": "polling", "websocket": False, "redis": False, "hot_cache": "sqlite+memory"},
            "buckets": _bucket_rows_from_db(),
            "events": [],
        }
        return {
            "data_status": "unavailable",
            "message": "No live scanner results are available. Run a live scan or configure a market data provider.",
            "provider": "yfinance",
            "last_updated": now(),
            "indices": indices,
            "kpis": {},
            "top_stocks": [],
            "top_opportunities": [],
            "watchlist": [],
            "news": news,
            "sector_heatmap": [],
            "risk": None,
            "breadth": None,
            "trade_availability": trade_availability,
            "ai_insights": [],
            "realtime": realtime,
        }
    strong_buy = [item for item in stocks if item["ai_rating"] == "Strong Buy"]
    avg_profitability = sum(item["profitability_score"] for item in stocks) / len(stocks)
    avg_risk = sum(item["risk_score"] for item in stocks) / len(stocks)
    advances = sum(1 for item in stocks if item["change_pct"] >= 0)
    declines = sum(1 for item in stocks if item["change_pct"] < 0)
    sectors: dict[str, dict[str, Any]] = {}
    for item in stocks:
        sector = item["sector"]
        sector_row = sectors.setdefault(sector, {"sector": sector, "count": 0, "profit": 0.0, "score": 0.0})
        sector_row["count"] += 1
        sector_row["profit"] += item["change_pct"]
        sector_row["score"] += item["final_ai_score"]
    sector_heatmap = []
    for item in sectors.values():
        count = max(item["count"], 1)
        sector_heatmap.append(
            {
                "sector": item["sector"],
                "count": item["count"],
                "profit": round(item["profit"] / count, 2),
                "score": round(item["score"] / count, 2),
            }
        )
    sector_heatmap.sort(key=lambda item: item["score"], reverse=True)
    market_sentiment = _market_sentiment_payload(
        stocks=stocks,
        indices=indices,
        sector_heatmap=sector_heatmap,
        avg_profitability=avg_profitability,
        avg_risk=avg_risk,
        strong_buy_count=len(strong_buy),
        advances=advances,
        declines=declines,
    )
    trade_availability = _trade_availability_from_scans(stocks)
    watchlist = rows(
        """
        SELECT s.symbol, s.name, s.sector, latest.price AS live_price, latest.change_pct, ps.final_ai_score
        FROM watchlist_items wi
        JOIN stocks s ON s.id = wi.stock_id
        JOIN profitability_scores ps ON ps.stock_id = s.id
        JOIN (
          SELECT sp1.* FROM stock_prices sp1
          JOIN (SELECT stock_id, MAX(id) AS max_id FROM stock_prices GROUP BY stock_id) x ON x.max_id = sp1.id
        ) latest ON latest.stock_id = s.id
        WHERE wi.watchlist_id = 1
          AND wi.created_at >= ?
        ORDER BY ps.final_ai_score DESC
        LIMIT 6
        """,
        (user_data_cutoff(),),
    )
    ai_insights = [
        {"title": "Top AI Pick", "symbol": stocks[0]["symbol"], "rating": stocks[0]["ai_rating"], "reason": stocks[0]["reasoning"]},
        {
            "title": "Best Value",
            "symbol": min(stocks, key=lambda item: item["pe"])["symbol"],
            "rating": min(stocks, key=lambda item: item["pe"])["ai_rating"],
            "reason": min(stocks, key=lambda item: item["pe"])["reasoning"],
        },
        {
            "title": "Momentum Leader",
            "symbol": max(stocks, key=lambda item: item["momentum_score"])["symbol"],
            "rating": max(stocks, key=lambda item: item["momentum_score"])["ai_rating"],
            "reason": max(stocks, key=lambda item: item["momentum_score"])["reasoning"],
        },
        {
            "title": "Risk Watch",
            "symbol": max(stocks, key=lambda item: item["risk_score"])["symbol"],
            "rating": max(stocks, key=lambda item: item["risk_score"])["ai_rating"],
            "reason": max(stocks, key=lambda item: item["risk_score"])["reasoning"],
        },
    ]
    realtime_buckets = store_realtime_snapshots(stocks, indices, ai_insights)
    realtime_updated_at = _latest_snapshot_time()
    return {
        "indices": indices,
        "data_status": "live",
        "last_updated": now(),
        "kpis": {
            "total_opportunities": len(stocks),
            "avg_profitability_score": round(avg_profitability, 2),
            "strong_buy_count": len(strong_buy),
            "market_sentiment": market_sentiment["label"],
            "market_sentiment_score": market_sentiment["score"],
            "intraday_available": trade_availability["intraday"]["count"],
            "swing_available": trade_availability["swing"]["count"],
            "longterm_available": trade_availability["longterm"]["count"],
        },
        "market_sentiment": market_sentiment,
        "trade_availability": trade_availability,
        "top_stocks": stocks[:50],
        "top_opportunities": stocks[:5],
        "watchlist": watchlist,
        "news": news,
        "sector_heatmap": sector_heatmap[:8],
        "risk": {"score": round(avg_risk, 2), "label": "Low Risk" if avg_risk < 35 else "Medium Risk" if avg_risk < 65 else "High Risk"},
        "breadth": {
            "advances": advances,
            "declines": declines,
            "unchanged": max(0, len(stocks) - advances - declines),
            "advance_pct": round((advances / len(stocks)) * 100, 2),
            "decline_pct": round((declines / len(stocks)) * 100, 2),
        },
        "ai_insights": ai_insights,
        "realtime": {
            "status": "live",
            "generated_at": now(),
            "freshness": _freshness(realtime_updated_at),
            "connection": {"stream": "polling", "websocket": False, "redis": False, "hot_cache": "sqlite+memory"},
            "buckets": realtime_buckets,
            "events": [],
        },
    }
