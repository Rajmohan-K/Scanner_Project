from __future__ import annotations

from datetime import datetime
from typing import Any

from .router import build_scan_metadata


def _stock_symbol(row: dict[str, Any]) -> str:
    return str(row.get("stock") or row.get("symbol") or "").strip().upper()


def _candidate_rows(scan_payload: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    for key in ("final_top_10", "top_25", "ranked", "results", "filtered_150"):
        rows = scan_payload.get(key)
        if isinstance(rows, list) and rows:
            symbols_seen: set[str] = set()
            selected: list[dict[str, Any]] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                symbol = _stock_symbol(row)
                if not symbol or symbol in symbols_seen:
                    continue
                symbols_seen.add(symbol)
                selected.append(row)
                if len(selected) >= limit:
                    return selected
            return selected
    return []


def build_open_confirmation_payload(
    premarket_scan: dict[str, Any],
    *,
    market_open_time: str = "09:08",
) -> dict[str, Any]:
    rows = _candidate_rows(premarket_scan, 25)
    symbols = [_stock_symbol(row) for row in rows if _stock_symbol(row)]
    metadata = build_scan_metadata("open-confirmation", "open_confirmation")
    return {
        **metadata,
        "symbols": symbols,
        "period": "5d",
        "interval": "5m",
        "top_n": 10,
        "candidate_pool": min(25, max(1, len(symbols))),
        "validation_pool": 0,
        "strict_shortlist": False,
        "market_open_analysis": True,
        "market_open_time": market_open_time,
        "market_open_interval": "1m",
        "source_scan_id": premarket_scan.get("scan_id"),
        "source_scan_mode": premarket_scan.get("scan_mode"),
        "source_stage": "premarket",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def build_intraday_payload(
    open_confirmation_scan: dict[str, Any],
    *,
    interval: str = "5m",
) -> dict[str, Any]:
    rows = _candidate_rows(open_confirmation_scan, 10)
    symbols = [_stock_symbol(row) for row in rows if _stock_symbol(row)]
    metadata = build_scan_metadata("intraday", "intraday_elite")
    return {
        **metadata,
        "symbols": symbols,
        "period": "30d",
        "interval": interval,
        "top_n": 10,
        "candidate_pool": min(10, max(1, len(symbols))),
        "validation_pool": 0,
        "strict_shortlist": False,
        "market_open_analysis": True,
        "market_open_time": "09:08",
        "market_open_interval": "1m",
        "source_scan_id": open_confirmation_scan.get("scan_id"),
        "source_scan_mode": open_confirmation_scan.get("scan_mode"),
        "source_stage": "open_confirmation",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def pipeline_snapshot(scans: list[dict[str, Any]]) -> dict[str, Any]:
    stages = {"premarket": None, "open_confirmation": None, "intraday": None}
    for scan in scans:
        family = str(scan.get("scan_family") or scan.get("scanner_bucket") or scan.get("scan_mode") or "").lower()
        if "open" in family and not stages["open_confirmation"]:
            stages["open_confirmation"] = scan
        elif "premarket" in family and not stages["premarket"]:
            stages["premarket"] = scan
        elif "intraday" in family and not stages["intraday"]:
            stages["intraday"] = scan
    return {
        "status": "ok",
        "pipeline": "premarket-open-confirmation-intraday",
        "stages": stages,
        "ready_for_open_confirmation": bool(stages["premarket"]),
        "ready_for_intraday": bool(stages["open_confirmation"]),
    }
