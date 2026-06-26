from __future__ import annotations

from ui import v20_store, v30_store
from scanners.meta_scanner import build_meta_scan


def _use_temp_db(monkeypatch, tmp_path):
    import ui.pg_store as pg_store
    pg_store._SHARED_MOCK_DB = None
    monkeypatch.setattr(v20_store, "DB_PATH", tmp_path / "v30.sqlite")
    monkeypatch.setattr(v20_store, "LIVE_PURGE_MARKER", tmp_path / ".v30_purge_done")
    monkeypatch.setattr(v20_store, "_DB_READY", False)
    v30_store.ensure_v30_schema()
    with v20_store.connect() as conn:
        try:
            conn.execute("DELETE FROM scanner_results")
            conn.execute("DELETE FROM scan_runs")
            conn.execute("DELETE FROM trade_plans")
        except Exception:
            pass


def _scan_body(scan_type: str, family: str, symbol: str, decision: str = "BUY") -> dict:
    return {
        "status": "ok",
        "scan_mode": scan_type,
        "scan_family": family,
        "scanner_bucket": family,
        "pipeline_stage": family,
        "message": f"{family} complete",
        "symbols_scanned": 1,
        "candidates_considered": 1,
        "summary": {"qualified": 1},
        "final_top_10": [
            {
                "stock": symbol,
                "symbol": symbol,
                "score": 88,
                "ml_probability": 82,
                "risk_score": 30,
                "risk_reward": 2.4,
                "premarket_action": decision,
                "reason": f"{family} reason",
                "entry": 100,
                "stop_loss": 95,
                "target1": 110,
                "target2": 120,
                "scan_family": family,
                "scanner_bucket": family,
                "pipeline_stage": family,
            }
        ],
    }


def test_v30_persists_scanner_results_with_separate_scan_families(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)

    cases = [
        ("run-intraday", "intraday", "intraday", "INTRA.NS"),
        ("run-premarket", "premarket", "premarket", "PRE.NS"),
        ("run-swing", "swing", "swing", "SWING.NS"),
        ("run-groww", "groww-intraday", "groww", "GROWW.NS"),
        ("run-meta", "meta", "meta", "META.NS"),
        ("run-final", "final-decision", "final_decision", "FINAL.NS"),
    ]
    for run_id, scan_type, family, symbol in cases:
        v30_store.persist_scan_run(run_id, _scan_body(scan_type, family, symbol), status="completed")

    rows = v20_store.rows(
        "SELECT scanner_run_id, scan_type, scan_family, scanner_bucket, pipeline_stage, symbol FROM scanner_results ORDER BY scanner_run_id"
    )
    by_family = {row["scan_family"]: row["symbol"] for row in rows}
    assert by_family["intraday"] == "INTRA.NS"
    assert by_family["premarket"] == "PRE.NS"
    assert by_family["swing"] == "SWING.NS"
    assert by_family["groww"] == "GROWW.NS"
    assert by_family["meta"] == "META.NS"
    assert by_family["final_decision"] == "FINAL.NS"


def test_v30_loads_latest_scan_from_database_not_archive(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    v30_store.persist_scan_run("run-intraday", _scan_body("intraday", "intraday", "INTRA.NS"), status="completed")
    v30_store.persist_scan_run("run-swing", _scan_body("swing", "swing", "SWING.NS"), status="completed")

    intraday = v30_store.latest_scan_for_family("intraday")
    swing = v30_store.latest_scan_for_family("swing")

    assert intraday is not None
    assert swing is not None
    assert intraday["final_top_10"][0]["symbol"] == "INTRA.NS"
    assert swing["final_top_10"][0]["symbol"] == "SWING.NS"
    assert intraday["source"] == "database"
    assert swing["source"] == "database"


def test_meta_scanner_uses_normalized_rows_and_keeps_source_families(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    v30_store.persist_scan_run("run-intraday", _scan_body("intraday", "intraday", "SHARED.NS"), status="completed")
    v30_store.persist_scan_run("run-swing", _scan_body("swing", "swing", "SHARED.NS"), status="completed")

    result = build_meta_scan("intraday")
    rows = [row for row in result["all_results"] if row["symbol"] == "SHARED.NS"]

    assert rows
    assert set(rows[0]["scan_types_matched"]) == {"intraday", "swing"}
    assert set(rows[0]["source_scan_ids"]) == {"run-intraday", "run-swing"}
    assert "final_decision" in rows[0]
