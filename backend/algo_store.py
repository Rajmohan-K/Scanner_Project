from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from ui import pg_store
from ui.v20_store import connect


_SCHEMA_READY = False


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _mock_table(name: str) -> list[dict[str, Any]] | None:
    if pg_store.get_pg_pool() != "MOCK":
        return None
    return pg_store.get_shared_mock_db().setdefault(name, [])


def ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    statements = [
        """CREATE TABLE IF NOT EXISTS algo_sessions (
            session_id VARCHAR(64) PRIMARY KEY, mode VARCHAR(20) NOT NULL, status VARCHAR(30) NOT NULL,
            capital DOUBLE PRECISION NOT NULL, available_funds DOUBLE PRECISION NOT NULL,
            max_trades INTEGER NOT NULL, max_loss DOUBLE PRECISION NOT NULL, risk_per_trade DOUBLE PRECISION NOT NULL,
            selected_trade_json TEXT, stop_reason TEXT, started_at VARCHAR(50), stopped_at VARCHAR(50),
            created_at VARCHAR(50) NOT NULL, updated_at VARCHAR(50) NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS algo_orders (
            order_id VARCHAR(64) PRIMARY KEY, session_id VARCHAR(64) NOT NULL, symbol VARCHAR(50) NOT NULL,
            side VARCHAR(10) NOT NULL, quantity INTEGER NOT NULL, remaining_quantity INTEGER NOT NULL,
            entry_price DOUBLE PRECISION NOT NULL, current_price DOUBLE PRECISION NOT NULL,
            initial_stop_loss DOUBLE PRECISION NOT NULL, stop_loss DOUBLE PRECISION NOT NULL,
            trailing_stop_loss DOUBLE PRECISION NOT NULL, target DOUBLE PRECISION NOT NULL,
            status VARCHAR(30) NOT NULL, pnl DOUBLE PRECISION NOT NULL DEFAULT 0,
            realized_pnl DOUBLE PRECISION NOT NULL DEFAULT 0, charges DOUBLE PRECISION NOT NULL DEFAULT 0,
            exit_reason TEXT, confidence DOUBLE PRECISION NOT NULL DEFAULT 0, strategy_reason TEXT,
            broker VARCHAR(30) NOT NULL DEFAULT 'dummy', source VARCHAR(30) NOT NULL DEFAULT 'yfinance',
            created_at VARCHAR(50) NOT NULL, updated_at VARCHAR(50) NOT NULL, closed_at VARCHAR(50))""",
        """CREATE TABLE IF NOT EXISTS algo_positions (
            position_id VARCHAR(64) PRIMARY KEY, order_id VARCHAR(64) UNIQUE NOT NULL, session_id VARCHAR(64) NOT NULL,
            symbol VARCHAR(50) NOT NULL, side VARCHAR(10) NOT NULL, quantity INTEGER NOT NULL,
            remaining_quantity INTEGER NOT NULL, average_price DOUBLE PRECISION NOT NULL,
            current_price DOUBLE PRECISION NOT NULL, unrealized_pnl DOUBLE PRECISION NOT NULL DEFAULT 0,
            realized_pnl DOUBLE PRECISION NOT NULL DEFAULT 0, status VARCHAR(30) NOT NULL,
            created_at VARCHAR(50) NOT NULL, updated_at VARCHAR(50) NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS algo_trades (
            trade_id VARCHAR(64) PRIMARY KEY, order_id VARCHAR(64) NOT NULL, session_id VARCHAR(64) NOT NULL,
            symbol VARCHAR(50) NOT NULL, side VARCHAR(10) NOT NULL, quantity INTEGER NOT NULL,
            entry_price DOUBLE PRECISION NOT NULL, exit_price DOUBLE PRECISION NOT NULL,
            gross_pnl DOUBLE PRECISION NOT NULL, charges DOUBLE PRECISION NOT NULL, net_pnl DOUBLE PRECISION NOT NULL,
            exit_reason TEXT, confidence DOUBLE PRECISION NOT NULL DEFAULT 0, strategy_reason TEXT,
            improvement_json TEXT, opened_at VARCHAR(50), closed_at VARCHAR(50) NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS algo_daily_performance (
            trade_date VARCHAR(20) PRIMARY KEY, capital DOUBLE PRECISION NOT NULL DEFAULT 0,
            total_trades INTEGER NOT NULL DEFAULT 0, winning_trades INTEGER NOT NULL DEFAULT 0,
            losing_trades INTEGER NOT NULL DEFAULT 0, realized_pnl DOUBLE PRECISION NOT NULL DEFAULT 0,
            unrealized_pnl DOUBLE PRECISION NOT NULL DEFAULT 0, charges DOUBLE PRECISION NOT NULL DEFAULT 0,
            net_pnl DOUBLE PRECISION NOT NULL DEFAULT 0, snapshots_json TEXT, updated_at VARCHAR(50) NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS broker_accounts (
            account_id VARCHAR(64) PRIMARY KEY, broker VARCHAR(30) NOT NULL, mode VARCHAR(20) NOT NULL,
            connected INTEGER NOT NULL DEFAULT 0, details_json TEXT, created_at VARCHAR(50) NOT NULL, updated_at VARCHAR(50) NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS broker_api_logs (
            log_id VARCHAR(64) PRIMARY KEY, broker VARCHAR(30) NOT NULL, action VARCHAR(60) NOT NULL,
            success INTEGER NOT NULL DEFAULT 0, request_json TEXT, response_json TEXT, error_message TEXT,
            created_at VARCHAR(50) NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS algo_watchlist_signals (
            symbol VARCHAR(50) PRIMARY KEY, company_name VARCHAR(100), side VARCHAR(10) NOT NULL,
            signal_type VARCHAR(50), entry_price DOUBLE PRECISION NOT NULL, current_price DOUBLE PRECISION NOT NULL,
            stop_loss DOUBLE PRECISION NOT NULL, target_1 DOUBLE PRECISION NOT NULL, target_2 DOUBLE PRECISION NOT NULL,
            trailing_sl DOUBLE PRECISION NOT NULL, confidence DOUBLE PRECISION NOT NULL, algo_score DOUBLE PRECISION NOT NULL,
            risk_reward DOUBLE PRECISION NOT NULL, status VARCHAR(30) NOT NULL, reason TEXT, updated_at VARCHAR(50) NOT NULL,
            ml_probability DOUBLE PRECISION NOT NULL DEFAULT 0, ai_reason TEXT, rejection_reason TEXT, auto_trade_allowed VARCHAR(10) NOT NULL DEFAULT 'NO',
            tech_score DOUBLE PRECISION NOT NULL DEFAULT 0, vol_score DOUBLE PRECISION NOT NULL DEFAULT 0, mom_score DOUBLE PRECISION NOT NULL DEFAULT 0,
            risk_score DOUBLE PRECISION NOT NULL DEFAULT 0, liq_score DOUBLE PRECISION NOT NULL DEFAULT 0, trend_score DOUBLE PRECISION NOT NULL DEFAULT 0,
            safety_score DOUBLE PRECISION NOT NULL DEFAULT 0)""",
        """CREATE TABLE IF NOT EXISTS algo_watchlist_rejections (
            symbol VARCHAR(50) PRIMARY KEY, company_name VARCHAR(100), reason TEXT NOT NULL,
            confidence DOUBLE PRECISION, volume_ratio DOUBLE PRECISION, risk_reward DOUBLE PRECISION,
            already_moved DOUBLE PRECISION, updated_at VARCHAR(50) NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS algo_execution_queue (
            symbol VARCHAR(50) PRIMARY KEY, side VARCHAR(10) NOT NULL, entry_price DOUBLE PRECISION NOT NULL,
            stop_loss DOUBLE PRECISION NOT NULL, target DOUBLE PRECISION NOT NULL, quantity INTEGER NOT NULL,
            capital_allocation DOUBLE PRECISION NOT NULL, confidence DOUBLE PRECISION NOT NULL, algo_score DOUBLE PRECISION NOT NULL,
            execution_status VARCHAR(30) NOT NULL, sent_to_algo VARCHAR(10) NOT NULL, updated_at VARCHAR(50) NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS algo_signal_history (
            history_id VARCHAR(64) PRIMARY KEY, symbol VARCHAR(50) NOT NULL, side VARCHAR(10) NOT NULL,
            entry_price DOUBLE PRECISION NOT NULL, stop_loss DOUBLE PRECISION NOT NULL, target DOUBLE PRECISION NOT NULL,
            confidence DOUBLE PRECISION NOT NULL, algo_score DOUBLE PRECISION NOT NULL, status VARCHAR(30) NOT NULL,
            reason TEXT, created_at VARCHAR(50) NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS algo_watchlist_custom_stocks (
            symbol VARCHAR(50) PRIMARY KEY, company_name VARCHAR(100), source VARCHAR(50) NOT NULL DEFAULT 'custom',
            monitoring_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE', created_at VARCHAR(50) NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS algo_watchlist_config (
            key VARCHAR(100) PRIMARY KEY, value TEXT NOT NULL)""",
    ]
    with connect() as conn:
        try:
            conn.execute("DROP TABLE IF EXISTS algo_watchlist_signals")
            conn.execute("DROP TABLE IF EXISTS algo_watchlist_rejections")
        except Exception:
            pass
        for statement in statements:
            conn.execute(statement)
    for name in (
        "algo_sessions", "algo_orders", "algo_positions", "algo_trades", "algo_daily_performance",
        "broker_accounts", "broker_api_logs", "algo_watchlist_signals", "algo_watchlist_rejections",
        "algo_execution_queue", "algo_signal_history", "algo_watchlist_custom_stocks", "algo_watchlist_config"
    ):
        _mock_table(name)
    _SCHEMA_READY = True


def clear_table(table: str) -> None:
    ensure_schema()
    mock = _mock_table(table)
    if mock is not None:
        mock.clear()
        return
    with connect() as conn:
        conn.execute(f"DELETE FROM {table}")



def insert(table: str, row: dict[str, Any]) -> dict[str, Any]:
    ensure_schema()
    mock = _mock_table(table)
    if mock is not None:
        mock.append(dict(row))
        return dict(row)
    columns = list(row)
    placeholders = ", ".join("?" for _ in columns)
    with connect() as conn:
        conn.execute(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})", tuple(row[column] for column in columns))
    return dict(row)


def update(table: str, key: str, value: Any, changes: dict[str, Any]) -> dict[str, Any] | None:
    ensure_schema()
    mock = _mock_table(table)
    if mock is not None:
        for row in mock:
            if row.get(key) == value:
                row.update(changes)
                return dict(row)
        return None
    assignments = ", ".join(f"{column} = ?" for column in changes)
    with connect() as conn:
        conn.execute(f"UPDATE {table} SET {assignments} WHERE {key} = ?", (*changes.values(), value))
    return get_one(table, key, value)


def list_rows(table: str) -> list[dict[str, Any]]:
    ensure_schema()
    mock = _mock_table(table)
    if mock is not None:
        return [dict(row) for row in mock]
    with connect() as conn:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table}").fetchall()]


def get_one(table: str, key: str, value: Any) -> dict[str, Any] | None:
    return next((row for row in list_rows(table) if row.get(key) == value), None)


def session_rows(session_id: str | None = None) -> list[dict[str, Any]]:
    rows = list_rows("algo_sessions")
    if session_id:
        rows = [row for row in rows if row.get("session_id") == session_id]
    return sorted(rows, key=lambda row: str(row.get("created_at") or ""), reverse=True)


def order_rows(session_id: str | None = None) -> list[dict[str, Any]]:
    rows = list_rows("algo_orders")
    if session_id:
        rows = [row for row in rows if row.get("session_id") == session_id]
    return sorted(rows, key=lambda row: str(row.get("created_at") or ""), reverse=True)


def position_rows(session_id: str | None = None) -> list[dict[str, Any]]:
    rows = list_rows("algo_positions")
    if session_id:
        rows = [row for row in rows if row.get("session_id") == session_id]
    return sorted(rows, key=lambda row: str(row.get("updated_at") or ""), reverse=True)


def trade_rows(today_only: bool = False, session_id: str | None = None) -> list[dict[str, Any]]:
    rows = list_rows("algo_trades")
    if today_only:
        prefix = date.today().isoformat()
        rows = [row for row in rows if str(row.get("closed_at") or "").startswith(prefix)]
    if session_id:
        rows = [row for row in rows if row.get("session_id") == session_id]
    for row in rows:
        try:
            row["improvement"] = json.loads(row.get("improvement_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            row["improvement"] = {}
    return sorted(rows, key=lambda row: str(row.get("closed_at") or ""), reverse=True)
