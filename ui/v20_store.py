from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from data.market_data_provider import get_market_data_provider
from ui.storage import list_scans, load_scan
from utils.logger import logger
import ui.pg_store as pg_store
from ui.redis_cache import get_redis_client, LiveSnapshotCache


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "ui" / "data" / "v20.sqlite"
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
LIVE_PURGE_MARKER = PROJECT_ROOT / ".scanner_cache" / ".v20_live_purge_v3_done"
LIVE_REFRESH_SECONDS = 60
REALTIME_REFRESH_SECONDS = 1
REALTIME_STALE_SECONDS = 90
_LAST_LIVE_REFRESH: datetime | None = None
_LAST_REALTIME_REFRESH: datetime | None = None
_LAST_HOT_CACHE_REFRESH: datetime | None = None
_LAST_SUPPORTING_REFRESH: datetime | None = None
_DB_READY = False


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect() -> Any:
    pool = pg_store.get_pg_pool()
    if pool == "MOCK":
        return pg_store.MockConnection()
    return pg_store.PSQLConnectionAdapter(pool.getconn(), pool)


def ensure_db() -> None:
    global _DB_READY
    if _DB_READY:
        return
    pg_store.ensure_pg_db()
    timestamp = now()
    try:
        pg_store.execute(
            "INSERT INTO users(id, email, name, role, created_at, updated_at) VALUES(1, %s, %s, %s, %s, %s) ON CONFLICT(id) DO NOTHING",
            ("analyst@scanner.local", "Default Analyst", "admin", timestamp, timestamp),
        )
        # Fetch the actual user_id of the seeded analyst to avoid foreign key violations
        user_rows = pg_store.rows("SELECT id FROM users WHERE email = %s", ("analyst@scanner.local",))
        if user_rows:
            user_id = user_rows[0]["id"]
            pg_store.execute(
                "INSERT INTO watchlists(id, user_id, name, created_at, updated_at) VALUES(1, %s, %s, %s, %s) ON CONFLICT(id) DO NOTHING",
                (user_id, "My Watchlist", timestamp, timestamp),
            )
            pg_store.execute(
                "INSERT INTO portfolios(id, user_id, name, created_at, updated_at) VALUES(1, %s, %s, %s, %s) ON CONFLICT(id) DO NOTHING",
                (user_id, "Core Portfolio", timestamp, timestamp),
            )
        else:
            logger.warning("Default analyst user could not be seeded or found.")
    except Exception as e:
        logger.warning(f"Error seeding database: {e}")
        
    purge_legacy_dummy_data()
    _DB_READY = True


def purge_legacy_dummy_data() -> None:
    if LIVE_PURGE_MARKER.exists():
        return
    try:
        with connect() as conn:
            for table in (
                "watchlist_items",
                "portfolio_holdings",
                "alerts",
                "paper_trades",
                "profitability_scores",
                "financial_metrics",
                "stock_prices",
                "stocks",
                "market_indices",
                "news_articles",
            ):
                conn.execute(f"DELETE FROM {table}")
    except Exception as e:
        logger.warning(f"Error purging legacy data: {e}")
        
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


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    import pandas as pd
    while isinstance(value, (pd.Series, pd.DataFrame)):
        if value.empty:
            return default
        value = value.iloc[0]
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _maybe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    import pandas as pd
    while isinstance(value, (pd.Series, pd.DataFrame)):
        if value.empty:
            return None
        value = value.iloc[0]
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
    clauses = ["payload IS NOT NULL", "payload != ''"]
    params: list[Any] = []
    if family:
        family_like = f"%{family.replace('-', '_')}%"
        alt_like = f"%{family.replace('_', '-')}%"
        clauses.append(
            "(scan_family LIKE %s OR scanner_bucket LIKE %s OR pipeline_stage LIKE %s OR scan_type LIKE %s "
            "OR scan_family LIKE %s OR scanner_bucket LIKE %s OR pipeline_stage LIKE %s OR scan_type LIKE %s)"
        )
        params.extend([family_like, family_like, family_like, family_like, alt_like, alt_like, alt_like, alt_like])
    params.append(max(1, min(int(limit or 500), 2000)))
    query = f"""
        SELECT scanner_run_id, scan_type, scan_family, scanner_bucket, pipeline_stage,
               result_bucket, result_role, symbol, rank, payload, updated_at
        FROM scanner_results
        WHERE {' AND '.join(clauses)}
        ORDER BY updated_at DESC, scanner_run_id DESC, rank ASC, id ASC
        LIMIT %s
    """
    try:
        db_rows = rows(query, tuple(params))
    except Exception:
        return []
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in db_rows:
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
    rows_out: list[dict[str, Any]] = []
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
                rows_out.extend([item for item in values if isinstance(item, dict)])
        if rows_out:
            break
    return rows_out


def ingest_latest_scan() -> None:
    rows_in = _stock_rows_from_scans()
    if not rows_in:
        return
    provider = get_market_data_provider()
    timestamp = now()
    for row in rows_in:
        symbol = str(row.get("symbol") or row.get("stock") or "").upper()
        if not symbol:
            continue
        live_quote = provider.get_quote(symbol)
        live_metrics = provider.get_financial_metrics(symbol)
        name = str(live_metrics.get("name") or row.get("name") or row.get("company_name") or symbol)
        sector = str(live_metrics.get("sector") or row.get("sector") or "Unclassified")
        industry = str(live_metrics.get("industry") or row.get("industry") or sector)
        market_cap = _as_float(live_metrics.get("market_cap"), _as_float(row.get("market_cap"), _as_float(row.get("market_cap_cr"), 0)))
        
        execute(
            """
            INSERT INTO stocks(symbol, name, sector, industry, market_cap, created_at, updated_at)
            VALUES(%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(symbol) DO UPDATE SET
              name=excluded.name, sector=excluded.sector, industry=excluded.industry,
              market_cap=excluded.market_cap, updated_at=excluded.updated_at
            """,
            (symbol, name, sector, industry, market_cap, timestamp, timestamp),
        )
        
        stock_rows = rows("SELECT id FROM stocks WHERE symbol=%s", (symbol,))
        if not stock_rows:
            continue
        stock_id = stock_rows[0]["id"]
        
        price = _as_float(live_quote.get("current_price"), _as_float(row.get("live_price"), _as_float(row.get("current_price"), _as_float(row.get("last_close"), 0))))
        previous = _as_float(live_quote.get("previous_close"), 0)
        change = ((price - previous) / previous * 100) if price and previous else _as_float(row.get("change"), _as_float(row.get("change_pct"), 0))
        volume = _as_float(live_quote.get("volume"), _as_float(row.get("volume"), 0))
        if price > 0:
            execute(
                "INSERT INTO stock_prices(stock_id, price, change_pct, volume, price_date, created_at, updated_at) VALUES(%s, %s, %s, %s, %s, %s, %s)",
                (stock_id, price, change, volume, timestamp[:10], timestamp, timestamp),
            )
        scoring_row = {**row, **{key: value for key, value in live_metrics.items() if value not in (None, "")}}
        try:
            score = _score_from_row(scoring_row)
        except ValueError:
            continue
        
        execute(
            """
            INSERT INTO financial_metrics(stock_id, pe, peg, roe, roa, roce, debt_ratio, dividend_yield,
              revenue_growth, eps_growth, net_profit_margin, free_cash_flow, created_at, updated_at)
            VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        execute(
            """
            INSERT INTO profitability_scores(stock_id, profitability_score, growth_score, value_score,
              momentum_score, risk_score, quality_score, final_ai_score, explanation, created_at, updated_at)
            VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        execute(
            "DELETE FROM ai_recommendations WHERE stock_id=%s",
            (stock_id,),
        )
        execute(
            """
            INSERT INTO ai_recommendations(stock_id, rating, confidence, reasoning, created_at, updated_at)
            VALUES(%s, %s, %s, %s, %s, %s)
            """,
            (stock_id, score["rating"], score["final"], score["explanation"], timestamp, timestamp),
        )


def refresh_supporting_live_data() -> None:
    global _LAST_SUPPORTING_REFRESH
    current = datetime.now()
    if _LAST_SUPPORTING_REFRESH and (current - _LAST_SUPPORTING_REFRESH).total_seconds() < 30:
        return
    _LAST_SUPPORTING_REFRESH = current

    timestamp = now()
    provider = get_market_data_provider()
    for item in provider.get_indices():
        execute(
            """
            INSERT INTO market_indices(symbol, name, value, change_pct, created_at, updated_at)
            VALUES(%s, %s, %s, %s, %s, %s)
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
    
    for article in provider.get_news(limit=20):
        title = article.get("title")
        published_at = article.get("published_at") or timestamp
        exists = rows(
            "SELECT 1 FROM news_articles WHERE title = %s AND published_at = %s",
            (title, published_at)
        )
        if not exists:
            execute(
                """
                INSERT INTO news_articles(title, category, source, url, published_at, created_at, updated_at)
                VALUES(%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    title,
                    article.get("category") or "Market",
                    article.get("source") or "provider",
                    article.get("url") or "",
                    published_at,
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
        indices_data = provider.get_indices()
        stock_prices_to_insert = []
        if stock_limit > 0:
            stock_rows = rows(
                """
                SELECT s.id, s.symbol
                FROM stocks s
                JOIN profitability_scores ps ON ps.stock_id = s.id
                ORDER BY ps.final_ai_score DESC
                LIMIT %s
                """,
                (stock_limit,),
            )
            stocks_list = [{"id": row["id"], "symbol": row["symbol"]} for row in stock_rows]
            
            for stock in stocks_list:
                try:
                    quote = provider.get_quote(stock["symbol"], use_cache=False)
                    price = _as_float(quote.get("current_price"), 0)
                    if price > 0:
                        previous = _as_float(quote.get("previous_close"), 0)
                        change = ((price - previous) / previous * 100) if previous else 0
                        volume = _as_float(quote.get("volume"), 0)
                        stock_prices_to_insert.append((stock["id"], price, change, volume, timestamp[:10], timestamp, timestamp))
                        
                        # Cache snapshot in Redis
                        snapshot_data = {
                            "symbol": stock["symbol"],
                            "price": price,
                            "change_pct": change,
                            "volume": volume,
                            "updated_at": timestamp
                        }
                        LiveSnapshotCache.save_live_snapshot(stock["symbol"], snapshot_data)
                        LiveSnapshotCache.publish_delta(stock["symbol"], snapshot_data)
                except Exception as e:
                    logger.warning(f"Failed to get quote for {stock['symbol']} during refresh: {e}")

        # Update database indices
        for item in indices_data:
            execute(
                """
                INSERT INTO market_indices(symbol, name, value, change_pct, created_at, updated_at)
                VALUES(%s, %s, %s, %s, %s, %s)
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
            
        for price_row in stock_prices_to_insert:
            execute(
                "INSERT INTO stock_prices(stock_id, price, change_pct, volume, price_date, created_at, updated_at) VALUES(%s, %s, %s, %s, %s, %s, %s)",
                price_row,
            )
    except Exception as exc:
        logger.error(f"Failed to refresh realtime snapshot: {exc}")
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
    pass


def rows(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    ensure_db()
    return pg_store.rows(query, params)


def execute(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    ensure_db()
    return pg_store.execute(query, params)


def stock_query(filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    ensure_db()
    filters = filters or {}
    clauses = []
    params: list[Any] = []
    search = str(filters.get("search") or "").strip()
    if search:
        clauses.append("(s.symbol LIKE %s OR s.name LIKE %s OR s.sector LIKE %s)")
        like = f"%{search}%"
        params.extend([like, like, like])
    for key, column in {
        "sector": "s.sector",
        "rating": "ar.rating",
    }.items():
        value = filters.get(key)
        if value:
            clauses.append(f"{column} = %s")
            params.append(value)
    numeric_filters = {
        "min_profitability": "ps.profitability_score >= %s",
        "min_ai_score": "ps.final_ai_score >= %s",
        "max_risk": "ps.risk_score <= %s",
        "min_roe": "fm.roe >= %s",
        "max_pe": "fm.pe <= %s",
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
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    try:
        return rows(sql, tuple(params))
    except Exception:
        return []


def _scan_result_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows_out: list[dict[str, Any]] = []
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
            rows_out.append(row)
    return rows_out


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
    
    # Store quotes in database + Redis live cache
    for row in stocks:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        
        # Save to database
        execute(
            """
            INSERT INTO stock_prices(stock_id, price, change_pct, volume, price_date, created_at, updated_at)
            VALUES((SELECT id FROM stocks WHERE symbol=%s), %s, %s, %s, %s, %s, %s)
            """,
            (symbol, _as_float(row.get("live_price")), _as_float(row.get("change_pct")), _as_float(row.get("volume")), timestamp[:10], timestamp, timestamp),
        )
        
        # Cache snapshot in Redis
        snapshot_data = {
            "symbol": symbol,
            "price": _as_float(row.get("live_price")),
            "change_pct": _as_float(row.get("change_pct")),
            "volume": _as_float(row.get("volume")),
            "updated_at": timestamp
        }
        LiveSnapshotCache.save_live_snapshot(symbol, snapshot_data)
        LiveSnapshotCache.publish_delta(symbol, snapshot_data)

    for row in indices:
        symbol = str(row.get("symbol") or row.get("name") or "").strip().upper()
        if not symbol:
            continue
        execute(
            """
            INSERT INTO market_indices(symbol, name, value, change_pct, created_at, updated_at)
            VALUES(%s, %s, %s, %s, %s, %s)
            ON CONFLICT(symbol) DO UPDATE SET value=excluded.value, change_pct=excluded.change_pct, updated_at=excluded.updated_at
            """,
            (symbol, symbol, _as_float(row.get("value")), _as_float(row.get("change_pct")), timestamp, timestamp),
        )

    # Save to scanner snapshots table in DB
    execute("DELETE FROM scanner_snapshots")
    execute("DELETE FROM opportunity_rankings")
    for bucket, bucket_rows in buckets.items():
        for item in bucket_rows:
            payload = json.dumps(item, default=str)
            execute(
                """
                INSERT INTO scanner_snapshots(scan_type, symbol, score, grade, rank, decision, reason, payload, updated_at)
                VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (bucket, item["symbol"], item["score"], item["grade"], item["rank"], item["decision"], item["reason"], payload, timestamp),
            )
            execute(
                """
                INSERT INTO opportunity_rankings(bucket, symbol, rank, score, grade, risk_score, confidence_score, sector, payload, updated_at)
                VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
    _LAST_HOT_CACHE_REFRESH = datetime.now()
    return buckets


def _latest_snapshot_time() -> str:
    for query in (
        "SELECT MAX(updated_at) AS updated_at FROM opportunity_rankings",
        "SELECT MAX(updated_at) AS updated_at FROM market_indices",
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
    
    from ui.realtime_feed import realtime_feed_simulator
    stocks = stock_query({"limit": 150})
    
    indices = []
    for sym, name in (("^NSEI", "NIFTY 50"), ("^BSESN", "SENSEX")):
        quote = realtime_feed_simulator.get_quote(sym)
        if quote and quote.get("current_price") is not None:
            indices.append({
                "symbol": sym,
                "name": name,
                "value": quote.get("current_price"),
                "change_pct": quote.get("change_pct", 0.0),
                "updated_at": quote.get("updated_at"),
            })
            
    if not indices:
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
        _LAST_HOT_CACHE_REFRESH = datetime.now()

    bucket_rows = _opportunity_buckets_from_stocks(stocks) if stocks else _bucket_rows_from_db()
    
    last_success = realtime_feed_simulator.last_success_time
    updated_at = last_success.isoformat(timespec="seconds") if last_success else _latest_snapshot_time()
    freshness = _freshness(updated_at)
    
    if not stocks:
        status = "empty"
    elif freshness["stale"]:
        status = "stale"
    else:
        status = "live"
        
    return {
        "status": status,
        "generated_at": now(),
        "freshness": freshness,
        "connection": {
            "stream": "live-stream",
            "websocket": True,
            "redis": True,
            "hot_cache": "redis",
            "last_cache_refresh": _LAST_HOT_CACHE_REFRESH.isoformat(timespec="seconds") if _LAST_HOT_CACHE_REFRESH else "",
        },
        "provider_status": {
            "provider_name": realtime_feed_simulator.provider_name,
            "status": realtime_feed_simulator.status,
            "success_count": realtime_feed_simulator.success_count,
            "failure_count": realtime_feed_simulator.failure_count,
            "last_success_time": realtime_feed_simulator.last_success_time.isoformat() if realtime_feed_simulator.last_success_time else None,
            "last_scan_duration": realtime_feed_simulator.last_scan_duration,
            "next_scan_time": realtime_feed_simulator.next_scan_time.isoformat() if realtime_feed_simulator.next_scan_time else None,
            "error_reason": realtime_feed_simulator.error_reason,
            "is_auto_mode": realtime_feed_simulator.is_auto_mode,
        },
        "indices": indices,
        "buckets": bucket_rows,
        "ai_insights": ai_insights,
        "events": [],
    }


def dashboard_payload() -> dict[str, Any]:
    ensure_db()
    stocks = stock_query({"limit": 100})
    indices = rows("SELECT symbol, name, value, change_pct, updated_at FROM market_indices ORDER BY id")
    if not stocks:
        realtime = realtime_payload() if rows("SELECT 1 FROM opportunity_rankings LIMIT 1") else {
            "status": "empty",
            "generated_at": now(),
            "freshness": {"updated_at": "", "age_seconds": None, "stale": True},
            "connection": {"stream": "live-stream", "websocket": False, "redis": True, "hot_cache": "redis"},
            "buckets": _bucket_rows_from_db(),
            "events": [],
        }
        return {
            "data_status": "unavailable",
            "message": "No live scanner results are available.",
            "provider": "kotak",
            "last_updated": now(),
            "indices": indices,
            "top_stocks": [],
            "realtime": realtime,
        }
    realtime_buckets = store_realtime_snapshots(stocks, indices, [])
    realtime_updated_at = _latest_snapshot_time()
    return {
        "indices": indices,
        "data_status": "live",
        "last_updated": now(),
        "top_stocks": stocks[:50],
        "realtime": {
            "status": "live",
            "generated_at": now(),
            "freshness": _freshness(realtime_updated_at),
            "connection": {"stream": "live-stream", "websocket": True, "redis": True, "hot_cache": "redis"},
            "buckets": realtime_buckets,
            "events": [],
        },
    }


# --- V30 Merged Store Code ---
SCAN_ROW_BUCKETS = (
    "final_top_10",
    "ranked",
    "top_25",
    "filtered_150",
    "results",
    "all_stocks_live_data",
)

BUCKET_ROLE = {
    "final_top_10": "final",
    "ranked": "ranked",
    "top_25": "shortlist",
    "filtered_150": "candidate",
    "results": "analysis",
    "all_stocks_live_data": "universe",
}


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, default=str)


def _loads(value: Any, fallback: Any = None) -> Any:
    if value in (None, ""):
        return fallback
    try:
        return json.loads(str(value))
    except Exception:
        return fallback


def _float(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _symbol(row: dict[str, Any]) -> str:
    return str(row.get("symbol") or row.get("stock") or "").strip().upper()


def ensure_v30_schema() -> None:
    ensure_db()
