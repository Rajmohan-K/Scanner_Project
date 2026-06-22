from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from ui import v20_store


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


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


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


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except sqlite3.OperationalError:
        return set()


def _add_column(conn: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    if column not in _table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def ensure_v30_schema() -> None:
    v20_store.ensure_db()
    with v20_store.connect() as conn:
        conn.executescript(
            """
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
            """
        )
        for column, column_type in {
            "message": "TEXT",
            "report_path": "TEXT",
            "symbols_scanned": "INTEGER DEFAULT 0",
            "candidates_considered": "INTEGER DEFAULT 0",
            "summary_json": "TEXT",
            "scan_params_json": "TEXT",
            "payload_json": "TEXT",
            "archive_scan_id": "TEXT",
        }.items():
            _add_column(conn, "scan_runs", column, column_type)
        for column, column_type in {
            "scan_family": "TEXT",
            "scanner_bucket": "TEXT",
            "pipeline_stage": "TEXT",
            "result_bucket": "TEXT",
            "result_role": "TEXT",
            "score_json": "TEXT",
            "reasons_json": "TEXT",
            "risk_json": "TEXT",
            "trade_plan_json": "TEXT",
            "reason_rejected": "TEXT",
            "created_at": "TEXT",
        }.items():
            _add_column(conn, "scanner_results", column, column_type)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_v30_scan_runs_type_created ON scan_runs(scan_family, scanner_bucket, pipeline_stage, created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_v30_scanner_results_run_bucket ON scanner_results(scanner_run_id, result_bucket, rank)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_v30_scanner_results_family_symbol ON scanner_results(scan_family, scanner_bucket, symbol, updated_at DESC)"
        )


def _metadata(body: dict[str, Any]) -> dict[str, str]:
    scan_type = str(body.get("scan_mode") or body.get("scan_type") or "standard")
    scan_family = str(body.get("scan_family") or body.get("scanner_bucket") or scan_type or "standard")
    scanner_bucket = str(body.get("scanner_bucket") or scan_family)
    pipeline_stage = str(body.get("pipeline_stage") or scanner_bucket or "standalone")
    return {
        "scan_type": scan_type,
        "scan_family": scan_family,
        "scanner_bucket": scanner_bucket,
        "pipeline_stage": pipeline_stage,
    }


def _scan_rows(body: dict[str, Any]) -> list[tuple[str, int, dict[str, Any]]]:
    rows: list[tuple[str, int, dict[str, Any]]] = []
    for bucket in SCAN_ROW_BUCKETS:
        value = body.get(bucket)
        if not isinstance(value, list):
            continue
        for index, row in enumerate(value, start=1):
            if isinstance(row, dict) and _symbol(row):
                rows.append((bucket, index, row))
    return rows


def _score_payload(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "score",
        "final_score",
        "final_opportunity_score",
        "profitability_score",
        "growth_score",
        "value_score",
        "momentum_score",
        "quality_score",
        "technical_score",
        "fundamental_score",
        "ml_probability",
        "ml_score",
        "ai_confidence",
        "confidence_pct",
        "meta_score",
        "backtest_score",
        "risk_score",
    )
    return {key: row.get(key) for key in keys if row.get(key) not in (None, "")}


def _reason_payload(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "reason",
        "trade_reason",
        "reason_selected",
        "reason_rejected",
        "risk_warning",
        "quality_filter_reasons",
        "premarket_reasons",
        "decision_summary",
        "final_decision",
        "pattern",
        "setup_type",
    )
    return {key: row.get(key) for key in keys if row.get(key) not in (None, "", [])}


def _risk_payload(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "risk_score",
        "risk_level",
        "risk_warning",
        "stop_distance_pct",
        "data_reliability_score",
        "volatility",
        "atr",
    )
    return {key: row.get(key) for key in keys if row.get(key) not in (None, "")}


def _trade_plan_payload(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "entry",
        "entry_price",
        "entry_zone_low",
        "entry_zone_high",
        "stoploss",
        "stop_loss",
        "target1",
        "target_1",
        "target2",
        "target_2",
        "target3",
        "target_3",
        "risk_reward",
        "risk_reward_ratio",
        "rrr",
        "expected_return",
        "trade_type",
        "signal",
    )
    return {key: row.get(key) for key in keys if row.get(key) not in (None, "")}


def _row_score(row: dict[str, Any]) -> float | None:
    for key in (
        "final_opportunity_score",
        "profitability_score",
        "technical_score",
        "score",
        "ml_probability",
        "confidence_pct",
        "meta_score",
    ):
        value = _float(row.get(key))
        if value is not None:
            return value
    return None


def _row_decision(row: dict[str, Any]) -> str:
    return str(
        row.get("final_decision")
        or row.get("action")
        or row.get("premarket_action")
        or row.get("signal")
        or row.get("trade_type")
        or row.get("ai_rating")
        or row.get("recommendation")
        or "Watch"
    )


def _grade(row: dict[str, Any]) -> str:
    return str(row.get("trade_grade") or row.get("grade") or row.get("ai_rating") or _row_decision(row))


def _entry(row: dict[str, Any]) -> float | None:
    return _float(row.get("entry") or row.get("entry_price") or row.get("entry_zone_low"))


def _stop(row: dict[str, Any]) -> float | None:
    return _float(row.get("stop_loss") or row.get("stoploss"))


def _target(row: dict[str, Any], index: int) -> float | None:
    return _float(row.get(f"target{index}") or row.get(f"target_{index}"))


def persist_scan_run(scan_id: str, body: dict[str, Any], status: str = "completed") -> None:
    ensure_v30_schema()
    timestamp = now()
    metadata = _metadata(body)
    summary = body.get("summary") if isinstance(body.get("summary"), dict) else {}
    rows = _scan_rows(body)
    with v20_store.connect() as conn:
        conn.execute(
            """
            INSERT INTO scan_runs(
                id, scan_type, scan_family, scanner_bucket, pipeline_stage, status,
                source_scan_id, started_at, completed_at, total_candidates, selected_count,
                created_at, updated_at, message, report_path, symbols_scanned,
                candidates_considered, summary_json, scan_params_json, payload_json, archive_scan_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                scan_type=excluded.scan_type,
                scan_family=excluded.scan_family,
                scanner_bucket=excluded.scanner_bucket,
                pipeline_stage=excluded.pipeline_stage,
                status=excluded.status,
                source_scan_id=excluded.source_scan_id,
                completed_at=excluded.completed_at,
                total_candidates=excluded.total_candidates,
                selected_count=excluded.selected_count,
                updated_at=excluded.updated_at,
                message=excluded.message,
                report_path=excluded.report_path,
                symbols_scanned=excluded.symbols_scanned,
                candidates_considered=excluded.candidates_considered,
                summary_json=excluded.summary_json,
                scan_params_json=excluded.scan_params_json,
                payload_json=excluded.payload_json,
                archive_scan_id=excluded.archive_scan_id
            """,
            (
                scan_id,
                metadata["scan_type"],
                metadata["scan_family"],
                metadata["scanner_bucket"],
                metadata["pipeline_stage"],
                status,
                (body.get("scan_params") or {}).get("source_scan_id") or body.get("source_scan_id"),
                body.get("created_at") or timestamp,
                timestamp if status in {"completed", "error", "cancelled"} else None,
                _int(body.get("candidates_considered") or body.get("total_candidates")),
                len(body.get("final_top_10") or body.get("ranked") or []),
                body.get("created_at") or timestamp,
                timestamp,
                body.get("message"),
                body.get("report_path"),
                _int(body.get("symbols_scanned")),
                _int(body.get("candidates_considered")),
                _json(summary),
                _json(body.get("scan_params") or {}),
                _json(body),
                body.get("archive_scan_id"),
            ),
        )
        conn.execute("DELETE FROM scanner_results WHERE scanner_run_id=?", (scan_id,))
        conn.execute("DELETE FROM trade_plans WHERE scan_type=? AND payload LIKE ?", (metadata["scan_type"], f'%"scanner_run_id": "{scan_id}"%'))
        for bucket, rank, raw_row in rows:
            row = dict(raw_row)
            row.setdefault("symbol", _symbol(row))
            row.setdefault("stock", row["symbol"])
            row.setdefault("scan_type", metadata["scan_type"])
            row.setdefault("scan_family", row.get("scan_family") or metadata["scan_family"])
            row.setdefault("scanner_bucket", row.get("scanner_bucket") or metadata["scanner_bucket"])
            row.setdefault("pipeline_stage", row.get("pipeline_stage") or metadata["pipeline_stage"])
            score_payload = _score_payload(row)
            reasons = _reason_payload(row)
            risk = _risk_payload(row)
            trade_plan = _trade_plan_payload(row)
            payload = {
                **row,
                "scanner_run_id": scan_id,
                "result_bucket": bucket,
                "result_role": BUCKET_ROLE.get(bucket, bucket),
            }
            conn.execute(
                """
                INSERT INTO scanner_results(
                    scanner_run_id, scan_type, scan_family, scanner_bucket, pipeline_stage,
                    result_bucket, result_role, symbol, rank, score, grade, decision,
                    entry, stop_loss, target1, target2, target3, risk_reward,
                    confidence, reason_selected, reason_rejected, risk_warning,
                    score_json, reasons_json, risk_json, trade_plan_json, payload,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scan_id,
                    metadata["scan_type"],
                    row.get("scan_family") or metadata["scan_family"],
                    row.get("scanner_bucket") or metadata["scanner_bucket"],
                    row.get("pipeline_stage") or metadata["pipeline_stage"],
                    bucket,
                    BUCKET_ROLE.get(bucket, bucket),
                    row["symbol"],
                    rank,
                    _row_score(row),
                    _grade(row),
                    _row_decision(row),
                    _entry(row),
                    _stop(row),
                    _target(row, 1),
                    _target(row, 2),
                    _target(row, 3),
                    _float(row.get("risk_reward") or row.get("risk_reward_ratio") or row.get("rrr")),
                    _float(row.get("confidence_pct") or row.get("confidence") or row.get("ml_probability")),
                    str(row.get("reason_selected") or row.get("reason") or row.get("trade_reason") or ""),
                    str(row.get("reason_rejected") or ""),
                    str(row.get("risk_warning") or ""),
                    _json(score_payload),
                    _json(reasons),
                    _json(risk),
                    _json(trade_plan),
                    _json(payload),
                    timestamp,
                    timestamp,
                ),
            )
            if trade_plan:
                conn.execute(
                    """
                    INSERT INTO trade_plans(
                        symbol, scan_type, trade_type, entry_zone, stop_loss, target1,
                        target2, target3, risk_reward, confidence, invalidation_point,
                        reasoning, payload, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["symbol"],
                        metadata["scan_type"],
                        str(row.get("trade_type") or row.get("signal") or row.get("premarket_action") or ""),
                        str(row.get("entry_zone") or row.get("entry") or row.get("entry_price") or ""),
                        _stop(row),
                        _target(row, 1),
                        _target(row, 2),
                        _target(row, 3),
                        _float(row.get("risk_reward") or row.get("risk_reward_ratio") or row.get("rrr")),
                        _float(row.get("confidence_pct") or row.get("confidence") or row.get("ml_probability")),
                        str(row.get("invalidation_point") or ""),
                        str(row.get("reason") or row.get("trade_reason") or row.get("reason_selected") or ""),
                        _json({**trade_plan, "scanner_run_id": scan_id, "result_bucket": bucket}),
                        timestamp,
                        timestamp,
                    ),
                )


def update_scan_run_status(scan_id: str, status: str = "running", message: str | None = None) -> None:
    ensure_v30_schema()
    timestamp = now()
    with v20_store.connect() as conn:
        conn.execute(
            """
            UPDATE scan_runs
            SET status=?, updated_at=?, message=COALESCE(?, message)
            WHERE id=?
            """,
            (status, timestamp, message, scan_id),
        )


def _scan_run_where(family: str) -> tuple[str, tuple[Any, ...]]:
    family_like = f"%{family.replace('-', '_')}%"
    alt_like = f"%{family.replace('_', '-')}%"
    return (
        """
        WHERE status='completed' AND (
            scan_family LIKE ? OR scanner_bucket LIKE ? OR pipeline_stage LIKE ?
            OR scan_type LIKE ? OR scan_family LIKE ? OR scanner_bucket LIKE ?
            OR pipeline_stage LIKE ? OR scan_type LIKE ?
        )
        """,
        (family_like, family_like, family_like, family_like, alt_like, alt_like, alt_like, alt_like),
    )


def list_scan_runs(limit: int = 40, family: str | None = None) -> list[dict[str, Any]]:
    ensure_v30_schema()
    limit = max(1, min(int(limit or 40), 500))
    where = "WHERE status='completed'"
    params: tuple[Any, ...] = ()
    if family:
        where, params = _scan_run_where(family)
    query = f"""
        SELECT * FROM scan_runs
        {where}
        ORDER BY COALESCE(completed_at, updated_at, created_at) DESC
        LIMIT ?
    """
    result = []
    for row in v20_store.rows(query, (*params, limit)):
        summary = _loads(row.get("summary_json"), {}) or {}
        result.append(
            {
                "scan_id": row.get("id"),
                "id": row.get("id"),
                "created_at": row.get("created_at") or "",
                "updated_at": row.get("updated_at") or "",
                "completed_at": row.get("completed_at") or "",
                "message": row.get("message") or "",
                "scan_mode": row.get("scan_type") or "standard",
                "scan_type": row.get("scan_type") or "standard",
                "scan_family": row.get("scan_family") or "",
                "scanner_bucket": row.get("scanner_bucket") or "",
                "pipeline_stage": row.get("pipeline_stage") or "",
                "scanner_display_name": row.get("scanner_display_name") or row.get("scan_type") or "",
                "symbols_scanned": row.get("symbols_scanned") or 0,
                "candidates_considered": row.get("candidates_considered") or row.get("total_candidates") or 0,
                "qualified": summary.get("qualified") or row.get("selected_count") or 0,
                "avg_premarket_grade": summary.get("avg_premarket_grade") or 0,
                "avg_ml_probability": summary.get("avg_ml_probability") or 0,
                "intraday_ready": summary.get("intraday_ready") or 0,
                "swing_ready": summary.get("swing_ready") or 0,
                "source": "database",
            }
        )
    return result


def active_scan_runs(limit: int = 20) -> list[dict[str, Any]]:
    ensure_v30_schema()
    rows = v20_store.rows(
        """
        SELECT * FROM scan_runs
        WHERE status IN ('queued', 'running', 'paused', 'cancel_requested')
        ORDER BY COALESCE(updated_at, created_at) DESC
        LIMIT ?
        """,
        (max(1, min(int(limit or 20), 100)),),
    )
    output: list[dict[str, Any]] = []
    for row in rows:
        payload = _loads(row.get("scan_params_json"), {}) or {}
        status = str(row.get("status") or "running")
        output.append(
            {
                "active": True,
                "scan_id": row.get("id"),
                "id": row.get("id"),
                "scan_type": row.get("scan_type"),
                "scan_mode": row.get("scan_type"),
                "scan_family": row.get("scan_family"),
                "scanner_bucket": row.get("scanner_bucket"),
                "pipeline_stage": row.get("pipeline_stage"),
                "display_name": row.get("scanner_display_name") or row.get("scan_type"),
                "status": status,
                "progress": status.replace("_", " ").title(),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
                "payload": payload,
                "message": row.get("message"),
                "source": "database",
            }
        )
    return output


def _rows_for_scan(scan_id: str) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in SCAN_ROW_BUCKETS}
    rows = v20_store.rows(
        """
        SELECT * FROM scanner_results
        WHERE scanner_run_id=?
        ORDER BY result_bucket, rank ASC, id ASC
        """,
        (scan_id,),
    )
    for row in rows:
        bucket = str(row.get("result_bucket") or "results")
        if bucket not in output:
            output[bucket] = []
        payload = _loads(row.get("payload"), {}) or {}
        payload.update(
            {
                "symbol": row.get("symbol"),
                "stock": payload.get("stock") or row.get("symbol"),
                "scan_type": row.get("scan_type"),
                "scan_family": row.get("scan_family"),
                "scanner_bucket": row.get("scanner_bucket"),
                "pipeline_stage": row.get("pipeline_stage"),
                "result_bucket": bucket,
                "result_role": row.get("result_role"),
                "rank": row.get("rank"),
                "score": payload.get("score", row.get("score")),
                "decision": payload.get("decision", row.get("decision")),
                "updated_at": row.get("updated_at"),
            }
        )
        output[bucket].append(payload)
    return output


def load_scan_run(scan_id: str) -> dict[str, Any] | None:
    ensure_v30_schema()
    rows = v20_store.rows("SELECT * FROM scan_runs WHERE id=?", (scan_id,))
    if not rows:
        return None
    scan = rows[0]
    payload = _loads(scan.get("payload_json"), {}) or {}
    payload.update(
        {
            "scan_id": scan.get("id"),
            "id": scan.get("id"),
            "created_at": scan.get("created_at") or payload.get("created_at"),
            "updated_at": scan.get("updated_at") or payload.get("updated_at"),
            "completed_at": scan.get("completed_at") or payload.get("completed_at"),
            "status": scan.get("status") or payload.get("status") or "completed",
            "message": scan.get("message") or payload.get("message") or "",
            "report_path": scan.get("report_path") or payload.get("report_path"),
            "scan_mode": scan.get("scan_type") or payload.get("scan_mode") or "standard",
            "scan_family": scan.get("scan_family") or payload.get("scan_family") or "standard",
            "scanner_bucket": scan.get("scanner_bucket") or payload.get("scanner_bucket") or "standard",
            "pipeline_stage": scan.get("pipeline_stage") or payload.get("pipeline_stage") or "standalone",
            "summary": _loads(scan.get("summary_json"), payload.get("summary") or {}) or {},
            "scan_params": _loads(scan.get("scan_params_json"), payload.get("scan_params") or {}) or {},
            "archive_scan_id": scan.get("archive_scan_id") or payload.get("archive_scan_id"),
            "source": "database",
        }
    )
    for bucket, bucket_rows in _rows_for_scan(scan_id).items():
        payload[bucket] = bucket_rows
    return payload


def latest_scan_for_family(family: str) -> dict[str, Any] | None:
    scans = list_scan_runs(limit=1, family=family)
    if not scans:
        return None
    return load_scan_run(str(scans[0]["scan_id"]))


def scan_payloads(limit: int = 120, family: str | None = None) -> list[dict[str, Any]]:
    payloads = []
    for item in list_scan_runs(limit=limit, family=family):
        payload = load_scan_run(str(item.get("scan_id") or ""))
        if payload:
            payloads.append(payload)
    return payloads


def backfill_saved_scans(limit: int = 500) -> dict[str, Any]:
    ensure_v30_schema()
    from ui.storage import list_scans, load_scan

    imported = 0
    skipped = 0
    for summary in list_scans(limit=limit):
        scan_id = str(summary.get("scan_id") or "")
        if not scan_id:
            skipped += 1
            continue
        exists = v20_store.rows("SELECT id FROM scan_runs WHERE id=?", (scan_id,))
        if exists:
            skipped += 1
            continue
        payload = load_scan(scan_id)
        if not payload:
            skipped += 1
            continue
        payload.setdefault("scan_id", scan_id)
        payload.setdefault("archive_scan_id", scan_id)
        try:
            persist_scan_run(scan_id, payload, status=str(payload.get("status") or "completed"))
            imported += 1
        except Exception:
            skipped += 1
    return {"status": "ok", "imported": imported, "skipped": skipped}


def scanner_results_for_meta(limit_scans: int = 80) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for payload in scan_payloads(limit=limit_scans):
        for bucket in SCAN_ROW_BUCKETS:
            rows = payload.get(bucket)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, dict) and _symbol(row):
                    records.append({**row, "source_scan_id": payload.get("scan_id")})
    return records


OPPORTUNITY_BUCKETS = {
    "intraday": ("intraday_top_10", "intraday_watch_25"),
    "premarket": ("premarket_top_10",),
    "open-confirmation": ("open_confirmation_top_10",),
    "open_confirmation": ("open_confirmation_top_10",),
    "swing": ("swing_top_20",),
    "breakout": ("breakouts_top_10",),
    "breakouts": ("breakouts_top_10",),
    "momentum": ("momentum_top_10",),
    "top": (
        "intraday_top_10",
        "premarket_top_10",
        "open_confirmation_top_10",
        "swing_top_20",
        "breakouts_top_10",
        "momentum_top_10",
    ),
}


def opportunity_rows(kind: str = "top", limit: int = 50) -> dict[str, Any]:
    ensure_v30_schema()
    kind = str(kind or "top").strip().lower().replace("_", "-")
    buckets = OPPORTUNITY_BUCKETS.get(kind, (kind,))
    placeholders = ",".join("?" for _ in buckets)
    rows = v20_store.rows(
        f"""
        SELECT bucket, symbol, rank, score, grade, risk_score, confidence_score,
               sector, payload, updated_at
        FROM opportunity_rankings
        WHERE bucket IN ({placeholders})
        ORDER BY score DESC, rank ASC, updated_at DESC
        LIMIT ?
        """,
        (*buckets, max(1, min(int(limit or 50), 500))),
    )
    parsed = []
    updated_at = ""
    for row in rows:
        payload = _loads(row.get("payload"), {}) or {}
        parsed.append(
            {
                **payload,
                "bucket": row.get("bucket"),
                "symbol": row.get("symbol"),
                "rank": row.get("rank"),
                "score": row.get("score"),
                "grade": row.get("grade"),
                "risk_score": row.get("risk_score"),
                "confidence_score": row.get("confidence_score"),
                "sector": row.get("sector"),
                "updated_at": row.get("updated_at"),
            }
        )
        updated_at = max(updated_at, str(row.get("updated_at") or ""))
    stale = True
    age_seconds: int | None = None
    if updated_at:
        try:
            age_seconds = max(0, int((datetime.now() - datetime.fromisoformat(updated_at)).total_seconds()))
            stale = age_seconds > 90
        except ValueError:
            age_seconds = None
    return {
        "status": "ok" if parsed else "empty",
        "kind": kind,
        "buckets": buckets,
        "rows": parsed,
        "count": len(parsed),
        "freshness": {"updated_at": updated_at, "age_seconds": age_seconds, "stale": stale},
        "generated_at": now(),
        "source": "opportunity_rankings",
    }
