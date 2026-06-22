from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import re
import ssl
import sys
from collections import defaultdict
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except (AttributeError, RuntimeError):
        pass

from aiohttp import ClientConnectionResetError, web


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from main import DEFAULT_BENCHMARK, WATCHLIST, calculate_market_open_analysis, dispatch_scan_telegram, is_valid_symbol, normalize_symbol, run_scan  # noqa: E402
from config import V30_STREAM_INTERVAL_SECONDS, V30_STREAM_MAX_EVENTS  # noqa: E402
from data.market_data import get_live_quote, get_stock_data  # noqa: E402
from scanners.intraday_engine import analyze_intraday_symbols, quick_intraday_signal as build_quick_intraday_signal  # noqa: E402
from scanners.meta_scanner import build_meta_scan  # noqa: E402
from scanners.premarket_pipeline import build_intraday_payload, build_open_confirmation_payload, pipeline_snapshot  # noqa: E402
from scanners.router import build_scan_metadata, normalize_scan_mode, scanner_profile, tag_records  # noqa: E402
from scanners.services import IntradayScannerService  # noqa: E402
from ui.storage import (
    delete_strategy,
    list_scans,
    list_strategies,
    load_scan,
    load_settings,
    load_strategy,
    save_scan,
    save_settings,
    save_strategy,
    stock_history,
)  # noqa: E402
from ui import ai_intelligence, v20_store, v30_store  # noqa: E402
from ui.stock_data_service import encode_sse, normalize_stock_symbol, stock_data_service  # noqa: E402
from ui.watchlist_monitor import watchlist_monitor  # noqa: E402
from data.market_data_provider import get_market_data_provider  # noqa: E402
from utils.telegram import TelegramDeliveryError, send_telegram_messages, telegram_config_status  # noqa: E402
from utils.logger import logger  # noqa: E402


BASE_DIR = Path(__file__).resolve().parent
INDEX_HTML = BASE_DIR / "static" / "dashboard.html"


def _namespace_from_payload(payload: dict[str, Any]) -> argparse.Namespace:
    def _float_or_none(key: str) -> float | None:
        value = payload.get(key)
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            logger.warning(f"Ignoring invalid numeric scan payload value for {key}: {value}")
            return None

    def _int_value(key: str, default: int) -> int:
        value = payload.get(key, default)
        if value in (None, ""):
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            logger.warning(f"Ignoring invalid integer scan payload value for {key}: {value}")
            return default

    symbols_input = payload.get("symbols", [])
    if isinstance(symbols_input, str):
        raw_symbols = [
            symbol.strip()
            for symbol in symbols_input.replace(",", " ").split()
            if symbol.strip()
        ]
    elif isinstance(symbols_input, list):
        raw_symbols = [symbol.strip() for symbol in symbols_input if isinstance(symbol, str) and symbol.strip()]
    else:
        raw_symbols = []

    symbols = []
    for raw in raw_symbols:
        normalized = normalize_symbol(raw)
        if normalized and is_valid_symbol(normalized):
            symbols.append(normalized)
        else:
            logger.warning(f"Dropped invalid payload symbol: {raw}")

    if not symbols:
        symbols = WATCHLIST

    period = payload.get("period", "6mo")
    interval = payload.get("interval", "1d")
    profile = scanner_profile(payload.get("scan_mode") or payload.get("type") or "", payload.get("pipeline_stage"))
    scan_mode = profile.mode
    if "intraday" in scan_mode and str(interval).lower().endswith(("m", "h")):
        period = "60d" if str(interval).lower().endswith("h") else "30d"

    return argparse.Namespace(
        symbols=symbols,
        period=period,
        interval=interval,
        benchmark=payload.get("benchmark", DEFAULT_BENCHMARK),
        scan_mode=scan_mode,
        pipeline_stage=profile.stage,
        top_n=_int_value("top_n", profile.default_top_n),
        workers=_int_value("workers", 5),
        symbols_file=payload.get("symbols_file") or None,
        candidate_pool=_int_value("candidate_pool", profile.default_candidate_pool),
        validation_pool=_int_value("validation_pool", profile.default_validation_pool),
        strict_shortlist=bool(payload.get("strict_shortlist", False)),
        min_expected_return_pct=float(payload.get("min_expected_return_pct", 5) or 0),
        min_ml_probability=_float_or_none("min_ml_probability"),
        min_risk_reward=_float_or_none("min_risk_reward"),
        max_stop_distance_pct=_float_or_none("max_stop_distance_pct"),
        min_data_reliability_score=_float_or_none("min_data_reliability_score"),
        min_profitability_score=_float_or_none("min_profitability_score"),
        auto_nse_universe=bool(payload.get("auto_nse_universe", False)),
        refresh_universe=bool(payload.get("refresh_universe", False)),
        universe_output=payload.get("universe_output", "all_symbols.txt"),
        market_open_analysis=bool(payload.get("market_open_analysis", False)),
        enable_deep_validation=bool(payload.get("enable_deep_validation", False)),
        market_open_time=payload.get("market_open_time", "09:08"),
        market_open_interval=payload.get("market_open_interval", "1m"),
        notify_telegram=bool(payload.get("notify_telegram", False)),
        telegram_category=payload.get("telegram_category", "Premarket"),
    )


def _serialize_record(record: dict[str, Any]) -> dict[str, Any]:
    serializable: dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            serializable[key] = value
        else:
            serializable[key] = value
    return serializable


def _build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "qualified": 0,
            "avg_premarket_grade": 0,
            "avg_ml_probability": 0,
            "avg_confidence": 0,
            "intraday_ready": 0,
            "swing_ready": 0,
            "avg_event_score": 0,
        }

    qualified = sum(1 for item in results if item.get("premarket_status") == "Qualified")
    intraday_ready = sum(1 for item in results if item.get("best_horizon") == "Intraday")
    swing_ready = sum(1 for item in results if item.get("best_horizon") == "Swing")
    avg_premarket_grade = round(sum(float(item.get("premarket_grade", 0) or 0) for item in results) / len(results), 2)
    avg_ml_probability = round(sum(float(item.get("ml_probability", 0) or 0) for item in results) / len(results), 2)
    avg_confidence = round(sum(float(item.get("confidence_pct", 0) or 0) for item in results) / len(results), 2)
    avg_event_score = round(sum(float(item.get("event_score", 0) or 0) for item in results) / len(results), 2)
    return {
        "qualified": qualified,
        "avg_premarket_grade": avg_premarket_grade,
        "avg_ml_probability": avg_ml_probability,
        "avg_confidence": avg_confidence,
        "intraday_ready": intraday_ready,
        "swing_ready": swing_ready,
        "avg_event_score": avg_event_score,
    }


def _sector_heatmap(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in results:
        grouped[str(item.get("sector", "UNKNOWN") or "UNKNOWN")].append(item)

    rows = []
    for sector, entries in grouped.items():
        rows.append(
            {
                "sector": sector,
                "count": len(entries),
                "avg_score": round(sum(float(e.get("score", 0) or 0) for e in entries) / len(entries), 2),
                "avg_grade": round(sum(float(e.get("premarket_grade", 0) or 0) for e in entries) / len(entries), 2),
                "avg_ml": round(sum(float(e.get("ml_probability", 0) or 0) for e in entries) / len(entries), 2),
                "qualified": sum(1 for e in entries if e.get("premarket_status") == "Qualified"),
            }
        )
    return sorted(rows, key=lambda item: item["avg_grade"], reverse=True)


def _compare_with_previous(current_scan: dict[str, Any]) -> dict[str, Any]:
    scans = _db_first_list_scans(limit=2)
    if len(scans) < 2:
        return {"available": False}

    previous = _db_first_load_scan(scans[1]["scan_id"])
    if not previous:
        return {"available": False}

    current_stocks = {item.get("stock") for item in current_scan.get("results", [])}
    previous_stocks = {item.get("stock") for item in previous.get("results", [])}

    current_results = {item.get("stock"): item for item in current_scan.get("results", [])}
    previous_results = {item.get("stock"): item for item in previous.get("results", [])}

    # Enhanced comparison with new entrants, dropped setups, and movers
    rows = []

    # 1. New entrants - stocks in current but not in previous
    for stock in (current_stocks - previous_stocks):
        current = current_results[stock]
        rows.append({
            "stock": stock,
            "type": "new_entrant",
            "grade_change": float(current.get("premarket_grade", 0) or 0),
            "ml_change": float(current.get("ml_probability", 0) or 0),
            "score_change": float(current.get("score", 0) or 0),
            "current_action": current.get("premarket_action", ""),
            "previous_action": "N/A",
            "current_grade": float(current.get("premarket_grade", 0) or 0),
        })

    # 2. Dropped setups - stocks in previous but not in current
    for stock in (previous_stocks - current_stocks):
        prior = previous_results[stock]
        rows.append({
            "stock": stock,
            "type": "dropped",
            "grade_change": -float(prior.get("premarket_grade", 0) or 0),
            "ml_change": -float(prior.get("ml_probability", 0) or 0),
            "score_change": -float(prior.get("score", 0) or 0),
            "current_action": "N/A",
            "previous_action": prior.get("premarket_action", ""),
            "previous_grade": float(prior.get("premarket_grade", 0) or 0),
        })

    # 3. Grade movers - significant changes in existing stocks
    for stock in (current_stocks & previous_stocks):
        current = current_results[stock]
        prior = previous_results[stock]
        grade_change = round(float(current.get("premarket_grade", 0) or 0) - float(prior.get("premarket_grade", 0) or 0), 2)
        ml_change = round(float(current.get("ml_probability", 0) or 0) - float(prior.get("ml_probability", 0) or 0), 2)
        score_change = round(float(current.get("score", 0) or 0) - float(prior.get("score", 0) or 0), 2)

        # Only show if significant change (> 5 points)
        if abs(grade_change) > 5:
            rows.append({
                "stock": stock,
                "type": "grade_mover",
                "grade_change": grade_change,
                "ml_change": ml_change,
                "score_change": score_change,
                "current_action": current.get("premarket_action", ""),
                "previous_action": prior.get("premarket_action", ""),
                "direction": "up" if grade_change > 0 else "down",
            })

    # Sort: new entrants first, then movers by magnitude, then dropped
    rows.sort(key=lambda x: (
        (0 if x["type"] == "new_entrant" else 1 if x["type"] == "grade_mover" else 2),
        abs(x.get("grade_change", 0)),
    ), reverse=True)

    return {
        "available": True,
        "previous_scan_id": scans[1]["scan_id"],
        "new_entrants": [r for r in rows if r.get("type") == "new_entrant"],
        "dropped_setups": [r for r in rows if r.get("type") == "dropped"],
        "grade_movers": [r for r in rows if r.get("type") == "grade_mover"],
        "rows": rows[:30],
    }


def _watchlist_rows(scan_payload: dict[str, Any], horizon: str) -> list[dict[str, Any]]:
    rows = []
    for item in scan_payload.get("ranked", []):
        if horizon == "intraday" and item.get("best_horizon") != "Intraday":
            continue
        if horizon == "swing" and item.get("best_horizon") != "Swing":
            continue
        rows.append(
            {
                "stock": item.get("stock"),
                "current_price": item.get("live_price") or item.get("current_price") or item.get("last_close"),
                "action": item.get("premarket_action"),
                "horizon": item.get("best_horizon"),
                "entry": item.get("entry"),
                "stoploss": item.get("stoploss"),
                "target1": item.get("target1"),
                "target2": item.get("target2"),
                "premarket_grade": item.get("premarket_grade"),
                "ml_probability": item.get("ml_probability"),
            }
        )
    return rows


def _csv_response(rows: list[dict[str, Any]], filename: str) -> web.Response:
    buffer = io.StringIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    else:
        buffer.write("stock,action,horizon,entry,stoploss,target1,target2,premarket_grade,ml_probability\n")

    return web.Response(
        text=buffer.getvalue(),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        content_type="text/csv",
    )


# Background scan task management
import asyncio
import uuid
from typing import Dict

# Structure: {scan_id: {"task": asyncio.Task, "status": str, "result": dict|None, "payload": dict, "cancel_requested": bool}}
scan_tasks: Dict[str, dict] = {}
market_widget_cache: dict[str, Any] = {"updated_at": 0.0, "values": None, "refreshing": False}
realtime_snapshot_cache: dict[str, Any] = {"updated_at": 0.0, "values": None, "refreshing": False}
groww_intraday_cache: dict[str, Any] = {"updated_at": 0.0, "payload": None}


def _groww_ssl_context() -> ssl.SSLContext:
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        logger.warning("certifi CA bundle unavailable; using relaxed SSL context for Groww source fetch only.")
        return ssl._create_unverified_context()


def _load_symbol_universe() -> list[str]:
    for path in (PROJECT_ROOT / "all_symbols.txt", BASE_DIR / "all_symbols.txt"):
        if not path.exists():
            continue
        try:
            return [
                normalize_symbol(line.strip())
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip() and normalize_symbol(line.strip())
            ]
        except Exception as exc:
            logger.warning(f"Unable to load symbol universe from {path}: {exc}")
    return []


def _symbol_base(symbol: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(symbol).upper().replace(".NS", ""))


def _company_to_symbol_candidates(company: str, universe: list[str]) -> list[str]:
    cleaned = re.sub(r"[^A-Za-z0-9 ]", " ", company).upper()
    stop_words = {
        "LIMITED", "LTD", "INDIA", "TECHNOLOGIES", "TECHNOLOGY", "INDUSTRIES",
        "INDUSTRY", "ENGINEERING", "WORKS", "SERVICES", "CORPORATION", "CO",
        "COMPANY", "PRIVATE", "PVT", "BANK", "FINANCE", "FINANCIAL",
    }
    tokens = [token for token in cleaned.split() if token and token not in stop_words]
    if not tokens:
        return []

    scored: list[tuple[int, str]] = []
    joined = "".join(tokens)
    for symbol in universe:
        base = _symbol_base(symbol)
        score = 0
        if base == joined:
            score += 90
        if tokens[0] and base.startswith(tokens[0][: min(5, len(tokens[0]))]):
            score += 45
        score += sum(12 for token in tokens if len(token) >= 3 and token[: min(5, len(token))] in base)
        if score >= 45:
            scored.append((score, symbol))
    return [symbol for _, symbol in sorted(scored, reverse=True)[:3]]


def _fetch_groww_intraday_rows(limit: int = 80) -> dict[str, Any]:
    now = datetime.now().timestamp()
    cached = groww_intraday_cache.get("payload")
    if cached and int(cached.get("limit") or 0) >= limit and now - float(groww_intraday_cache.get("updated_at") or 0) < 60:
        return cached

    url = "https://groww.in/stocks/intraday"
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=12, context=_groww_ssl_context()) as response:
        html = response.read().decode("utf-8", errors="ignore")

    text = unescape(re.sub(r"<[^>]+>", "\n", html))
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    blacklist = {
        "Stocks", "Company", "Market price", "Volume", "Today", "Filters", "Apply",
        "Clear all", "Market cap(Cr)", "Turnover", "RSI", "MACD", "Index", "Sector",
        "Market Cap", "Sort by high volume", "Price change >1%", "52W Performance",
    }
    universe = _load_symbol_universe()
    rows: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for idx, line in enumerate(lines):
        if line in blacklist or len(line) < 3 or len(line) > 70:
            continue
        if re.search(r"[₹%+,\d]", line):
            continue
        if not re.search(r"[A-Za-z]", line):
            continue
        if line.lower().startswith(("image:", "invest in", "trade in", "track ", "get ", "start ")):
            continue
        lookahead = " ".join(lines[idx + 1: idx + 8])
        if "₹" not in lookahead:
            continue
        name_key = line.upper()
        if name_key in seen_names:
            continue
        candidates = _company_to_symbol_candidates(line, universe)
        symbol = candidates[0] if candidates else ""
        seen_names.add(name_key)
        rows.append({
            "company": line,
            "symbol": symbol,
            "source": url,
            "resolved": bool(symbol),
            "candidates": candidates,
        })
        if len(rows) >= limit:
            break

    payload = {
        "status": "ok",
        "source": url,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "limit": limit,
        "count": len(rows),
        "resolved_count": sum(1 for row in rows if row.get("resolved")),
        "rows": rows,
        "symbols": [row["symbol"] for row in rows if row.get("symbol")],
    }
    groww_intraday_cache["updated_at"] = now
    groww_intraday_cache["payload"] = payload
    return payload


def _scan_type_name(payload: dict[str, Any] | None, fallback: str = "standard") -> str:
    raw = fallback
    if payload:
        if payload.get("scanner_display_name"):
            return str(payload.get("scanner_display_name"))
        raw = str(payload.get("scan_mode") or payload.get("type") or payload.get("scan_type") or fallback)
    return scanner_profile(raw).display_name if raw else "Standard Scanner"


def _task_progress(status: str | None) -> str:
    if status == "completed":
        return "100%"
    if status == "paused":
        return "Paused"
    if status in {"running", "queued"}:
        return "Running"
    if status in {"error", "cancelled", "cancel_requested"}:
        return str(status).replace("_", " ").title()
    return "0%"


def _active_scan_snapshot() -> dict[str, Any] | None:
    rows = _active_scan_list()
    return rows[0] if rows else None


def _memory_scan_summary(scan_id: str, entry: dict[str, Any]) -> dict[str, Any]:
    payload = entry.get("payload") or {}
    status = entry.get("status") or "running"
    return {
        "active": True,
        "scan_id": scan_id,
        "scan_type": _scan_type_name(payload),
        "display_name": _scan_type_name(payload),
        "status": status,
        "progress": _task_progress(status),
        "created_at": entry.get("created_at"),
        "payload": payload,
        "cancel_requested": entry.get("cancel_requested", False),
        "pause_requested": entry.get("pause_requested", False),
        "source": "memory",
    }


def _scan_task_summary(scan_id: str, entry: dict[str, Any]) -> dict[str, Any]:
    payload = entry.get("payload") or {}
    status = entry.get("status") or "unknown"
    result = entry.get("result") or {}
    return {
        "active": status in {"queued", "running", "paused", "cancel_requested"},
        "scan_id": scan_id,
        "scan_type": _scan_type_name(payload),
        "display_name": _scan_type_name(payload),
        "status": status,
        "progress": _task_progress(status),
        "created_at": entry.get("created_at"),
        "payload": payload,
        "message": result.get("message") if isinstance(result, dict) else None,
        "cancel_requested": entry.get("cancel_requested", False),
        "pause_requested": entry.get("pause_requested", False),
        "source": "memory",
    }


def _active_scan_list() -> list[dict[str, Any]]:
    rows = [
        _scan_task_summary(scan_id, entry)
        for scan_id, entry in scan_tasks.items()
        if entry.get("status") in {"queued", "running", "paused", "cancel_requested"}
    ]
    memory_ids = {str(row.get("scan_id") or row.get("id") or "") for row in rows}
    try:
        for row in v30_store.active_scan_runs(limit=30):
            scan_id = str(row.get("scan_id") or row.get("id") or "")
            if scan_id and scan_id not in memory_ids:
                rows.append(row)
    except Exception as exc:
        logger.warning(f"DB active scan lookup skipped: {exc}")
    return sorted(rows, key=lambda item: item.get("created_at") or "", reverse=True)


async def _run_scan_in_thread(scan_id: str, payload: dict[str, Any]):
    """Run the blocking `run_scan` in a thread and store the result in `scan_tasks`."""
    try:
        args = _namespace_from_payload(payload)
        # Provide a cooperative cancellation hook to the scan function
        def _should_cancel():
            return bool(scan_tasks.get(scan_id, {}).get("cancel_requested"))
        def _should_pause():
            return bool(scan_tasks.get(scan_id, {}).get("pause_requested"))
        setattr(args, "should_cancel", _should_cancel)
        setattr(args, "should_pause", _should_pause)
        logger.info(f"Background scan {scan_id} started for {len(args.symbols)} symbols")
        worker = asyncio.create_task(asyncio.to_thread(run_scan, args))
        try:
            while not worker.done():
                status = "paused" if scan_tasks.get(scan_id, {}).get("pause_requested") else "running"
                v30_store.update_scan_run_status(scan_id, status=status, message=f"Scan {status}")
                await asyncio.sleep(8)
            result = await worker
        except asyncio.CancelledError:
            worker.cancel()
            v30_store.update_scan_run_status(scan_id, status="cancelled", message="Scan cancelled")
            raise
        # If cancel requested, do not save result as active
        if scan_tasks.get(scan_id, {}).get("cancel_requested"):
            logger.info(f"Background scan {scan_id} completed but was cancelled; discarding results")
            scan_tasks[scan_id]["status"] = "cancelled"
            scan_tasks[scan_id]["result"] = None
            metadata = build_scan_metadata(payload.get("scan_mode") or payload.get("type") or "standard", payload.get("pipeline_stage"))
            _persist_scan_run(scan_id, {**metadata, "scan_params": payload, "message": "Scan cancelled"}, status="cancelled")
            return

        body = _scan_response_body(result)
        metadata = build_scan_metadata(result.get("scan_mode") or payload.get("scan_mode", "standard"), result.get("pipeline_stage") or payload.get("pipeline_stage"))
        body.update(metadata)
        body["scan_params"] = payload
        body["scan_id"] = scan_id
        _persist_scan_run(scan_id, body)
        saved_id = save_scan({**body, "scanner_run_id": scan_id})
        body["archive_scan_id"] = saved_id
        _persist_scan_run(scan_id, body)
        body["saved_scans"] = _db_first_list_scans(limit=20)
        body["comparison"] = _compare_with_previous(body)
        try:
            if getattr(args, "notify_telegram", False):
                dispatch_scan_telegram(result, args)
        except Exception as exc:
            logger.error(f"Telegram dispatch failed for background scan: {exc}", exc_info=True)

        scan_tasks[scan_id]["status"] = "completed"
        scan_tasks[scan_id]["result"] = body
        logger.info(f"Background scan {scan_id} completed and archived as {saved_id}")
    except Exception as e:
        logger.error(f"Background scan {scan_id} failed: {e}", exc_info=True)
        scan_tasks[scan_id]["status"] = "error"
        scan_tasks[scan_id]["result"] = {"status": "error", "message": str(e)}
        metadata = build_scan_metadata(payload.get("scan_mode") or payload.get("type") or "standard", payload.get("pipeline_stage"))
        _persist_scan_run(scan_id, {**metadata, "scan_params": payload, "message": str(e)}, status="error")



def _scan_response_body(scan_output: dict[str, Any]) -> dict[str, Any]:
    metadata = build_scan_metadata(scan_output.get("scan_mode", "standard"), scan_output.get("pipeline_stage"))
    ranked_df = scan_output.get("ranked")
    ranked_records = []
    if ranked_df is not None and not getattr(ranked_df, "empty", True):
        ranked_records = [
            _serialize_record(record)
            for record in ranked_df.to_dict(orient="records")
        ]

    all_results = tag_records([
        _serialize_record(record)
        for record in scan_output.get("results", [])
    ], metadata)
    breadth = scan_output.get("breadth", {}) or {}
    filtered_results = []
    for record in all_results:
        stock = record.get("stock")
        if not stock or not isinstance(stock, str):
            logger.warning(f"Dropping invalid scan record without stock: {record}")
            continue
        normalized = normalize_symbol(stock)
        if not normalized:
            logger.warning(f"Dropping invalid scan record with bad stock: {stock}")
            continue
        record["stock"] = normalized
        filtered_results.append(record)

    summary = _build_summary(filtered_results)
    def _records(name: str) -> list[dict[str, Any]]:
        return tag_records([
            _serialize_record(record)
            for record in scan_output.get(name, [])
            if isinstance(record, dict)
        ], metadata)

    filtered_ranked = []
    for record in ranked_records:
        stock = record.get("stock")
        if not stock or not isinstance(stock, str):
            logger.warning(f"Dropping invalid ranked record without stock: {record}")
            continue
        normalized = normalize_symbol(stock)
        if not normalized:
            logger.warning(f"Dropping invalid ranked record with bad stock: {stock}")
            continue
        record["stock"] = normalized
        filtered_ranked.append(record)
    filtered_ranked = tag_records(filtered_ranked, metadata)

    body = {
        "status": scan_output.get("status", "error"),
        "message": scan_output.get("message", ""),
        "report_path": scan_output.get("report_path"),
        **metadata,
        "symbols_scanned": scan_output.get("symbols_scanned", 0),
        "candidates_considered": scan_output.get("candidates_considered", 0),
        "summary": summary,
        "ranked": filtered_ranked,
        "results": filtered_results,
        "all_stocks_live_data": _records("all_stocks_live_data"),
        "filtered_150": _records("filtered_150"),
        "top_25": _records("top_25"),
        "final_top_10": _records("final_top_10"),
        "breadth": breadth,
        "sector_heatmap": _sector_heatmap(filtered_results),
    }
    return body


def _persist_scan_run(scan_id: str, body: dict[str, Any], status: str = "completed") -> None:
    try:
        v30_store.persist_scan_run(scan_id, body, status=status)
    except Exception as exc:
        logger.warning(f"Unable to persist scan run {scan_id} to database: {exc}")


def _persist_meta_scan(payload: dict[str, Any]) -> str:
    run_id = datetime.now().strftime("meta_%Y%m%d_%H%M%S")
    try:
        summary = payload.get("summary") or {}
        v20_store.execute(
            """
            INSERT OR REPLACE INTO meta_scan_runs(
                id, timeframe, status, generated_at, symbols_analyzed, shown_count,
                trade_count, watch_count, rejected_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                payload.get("timeframe", "intraday"),
                payload.get("status", "ok"),
                payload.get("generated_at"),
                int(summary.get("symbols_analyzed") or 0),
                int(summary.get("shown") or 0),
                int(summary.get("trade") or 0),
                int(summary.get("watch") or 0),
                int(summary.get("rejected") or 0),
            ),
        )
        for row in payload.get("all_results") or []:
            v20_store.execute(
                """
                INSERT INTO meta_scan_results(
                    meta_scan_run_id, symbol, timeframe, scan_types_matched, meta_score,
                    scanner_agreement_score, ai_confidence, ml_confidence, risk_score,
                    backtest_score, final_decision, trade_grade, should_show,
                    should_trade, should_watch, should_reject, trade_plan,
                    reason_selected, reason_rejected, data_freshness
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    row.get("symbol") or row.get("stock"),
                    row.get("timeframe"),
                    json.dumps(row.get("scan_types_matched") or []),
                    row.get("meta_score"),
                    row.get("scanner_agreement_score"),
                    row.get("ai_confidence"),
                    row.get("ml_confidence"),
                    row.get("risk_score"),
                    row.get("backtest_score"),
                    row.get("final_decision"),
                    row.get("trade_grade"),
                    1 if row.get("should_show") else 0,
                    1 if row.get("should_trade") else 0,
                    1 if row.get("should_watch") else 0,
                    1 if row.get("should_reject") else 0,
                    json.dumps(row.get("trade_plan") or {}),
                    row.get("reason_selected"),
                    row.get("reason_rejected"),
                    row.get("data_freshness"),
                ),
            )
            for scan_id in row.get("source_scan_ids") or []:
                for family in row.get("scan_types_matched") or []:
                    v20_store.execute(
                        "INSERT INTO scanner_signal_links(meta_scan_run_id, symbol, source_scan_id, scan_family) VALUES (?, ?, ?, ?)",
                        (run_id, row.get("symbol") or row.get("stock"), scan_id, family),
                    )
        for agreement in payload.get("agreements") or []:
            v20_store.execute(
                "INSERT INTO scanner_agreements(meta_scan_run_id, symbol, scan_types, agreement_score) VALUES (?, ?, ?, ?)",
                (run_id, agreement.get("symbol"), json.dumps(agreement.get("scan_types") or []), agreement.get("agreement_score")),
            )
        for conflict in payload.get("conflicts") or []:
            for warning in conflict.get("warnings") or []:
                v20_store.execute(
                    "INSERT INTO scanner_conflicts(meta_scan_run_id, symbol, warning, risk_score) VALUES (?, ?, ?, ?)",
                    (run_id, conflict.get("symbol"), warning, conflict.get("risk_score")),
                )
    except Exception as exc:
        logger.warning(f"Unable to persist meta scan {run_id}: {exc}")
    return run_id


def _db_first_list_scans(limit: int = 40, family: str | None = None) -> list[dict[str, Any]]:
    try:
        scans = v30_store.list_scan_runs(limit=limit, family=family)
        if scans:
            return scans
        v30_store.backfill_saved_scans(limit=max(limit, 120))
        scans = v30_store.list_scan_runs(limit=limit, family=family)
        if scans:
            return scans
    except Exception as exc:
        logger.warning(f"DB-first scan list unavailable, using archive scan files: {exc}")
    return list_scans(limit=limit)


def _db_first_load_scan(scan_id: str) -> dict[str, Any] | None:
    try:
        payload = v30_store.load_scan_run(scan_id)
        if payload:
            return payload
    except Exception as exc:
        logger.warning(f"DB-first scan detail unavailable for {scan_id}, using archive scan file: {exc}")
    return load_scan(scan_id)


async def health(_: web.Request) -> web.Response:
    saved_scans = _db_first_list_scans(limit=1)
    latest_scan = saved_scans[0] if saved_scans else None
    return web.json_response({
        "status": "ok",
        "system_status": "ok",
        "api_status": "online",
        "data_feed_status": "scan data available" if latest_scan else "no saved scans",
        "scan_count": len(saved_scans),
        "latest_scan": latest_scan,
    }, dumps=lambda value: json.dumps(value, default=str))


def _latest_close(symbol: str) -> float | None:
    quote = get_live_quote(symbol, use_cache=False)
    for key in ("current_price", "regularMarketPrice", "open", "previous_close"):
        value = quote.get(key) if isinstance(quote, dict) else None
        if isinstance(value, (int, float)):
            return round(float(value), 2)

    df = get_stock_data(symbol, period="5d", interval="1d")
    if df is None or df.empty:
        return None
    close = df.get("Close")
    if close is None:
        return None
    try:
        if hasattr(close, "columns"):
            return round(float(close.iloc[-1, 0]), 2)
        return round(float(close.iloc[-1]), 2)
    except Exception:
        return None


async def market_widgets(_: web.Request) -> web.Response:
    now_ts = datetime.now().timestamp()
    cached_values = market_widget_cache.get("values")
    active_scan = _active_scan_snapshot()
    if cached_values and now_ts - float(market_widget_cache.get("updated_at", 0)) < 5:
        values = dict(cached_values)
        if active_scan:
            scan_name = active_scan.get("scan_type") or active_scan.get("display_name") or "Live Scan"
            values.update({
                "currentScan": scan_name,
                "scanType": scan_name,
                "scanStatus": active_scan.get("status") or "running",
                "progress": active_scan.get("progress") or "running",
            })
        return web.json_response(values, dumps=lambda value: json.dumps(value, default=str))

    latest_scans = _db_first_list_scans(limit=1)
    latest_scan = latest_scans[0] if latest_scans else None
    scan_name = active_scan["scan_type"] if active_scan else _scan_type_name(latest_scan, "completed scan")
    scan_status = active_scan["status"] if active_scan else ("completed" if latest_scan else "idle")
    progress = active_scan["progress"] if active_scan else ("100%" if latest_scan else "0%")
    async def _timed_latest_close(symbol: str) -> float | None:
        try:
            return await asyncio.wait_for(asyncio.to_thread(_latest_close, symbol), timeout=1.8)
        except Exception as exc:
            logger.warning(f"Market widget quote timeout for {symbol}: {exc}")
            return None

    index_values = await asyncio.gather(
        _timed_latest_close("^NSEI"),
        _timed_latest_close("^NSEBANK"),
        _timed_latest_close("^BSESN"),
    )
    nse_value, bank_nifty_value, sensex_value = index_values
    values = {
        "nse_index": nse_value,
        "nifty_50": nse_value,
        "bank_nifty": bank_nifty_value,
        "sensex": sensex_value,
        "top_gainers": "Run scan to rank",
        "top_losers": "Run scan to rank",
        "currentScan": scan_name if latest_scan or active_scan else "No scan yet",
        "scanType": scan_name if latest_scan or active_scan else "No scan yet",
        "scanStatus": scan_status,
        "progress": progress,
        "lastScan": latest_scan.get("created_at") if latest_scan else "No completed scan",
        "lastAnalysis": latest_scan.get("message") if latest_scan else "No completed scan",
        "breadth": (
            f"{latest_scan.get('qualified', 0)} qualified / {latest_scan.get('symbols_scanned', 0)} scanned"
            if latest_scan
            else "No completed scan"
        ),
    }
    market_widget_cache["values"] = values
    market_widget_cache["updated_at"] = now_ts
    return web.json_response(values, dumps=lambda value: json.dumps(value, default=str))


async def active_scan(_: web.Request) -> web.Response:
    active = _active_scan_snapshot()
    if active:
        return web.json_response(active, dumps=lambda value: json.dumps(value, default=str))

    scans = _db_first_list_scans(limit=1)
    latest_scan = scans[0] if scans else None
    if not latest_scan:
        return web.json_response({
            "active": False,
            "scan_type": "No Scan Yet",
            "display_name": "No Scan Yet",
            "status": "idle",
            "progress": "0%",
        })

    return web.json_response({
        "active": False,
        "scan_id": latest_scan.get("scan_id"),
        "scan_type": _scan_type_name(latest_scan, "completed scan"),
        "display_name": _scan_type_name(latest_scan, "completed scan"),
        "status": "completed",
        "progress": "100%",
        "created_at": latest_scan.get("created_at"),
        "message": latest_scan.get("message"),
    }, dumps=lambda value: json.dumps(value, default=str))


async def active_scans(_: web.Request) -> web.Response:
    rows = _active_scan_list()
    return web.json_response({
        "active_count": len(rows),
        "active_scans": rows,
        "scans": rows,
    }, dumps=lambda value: json.dumps(value, default=str))


async def index(_: web.Request) -> web.Response:
    return web.Response(text=INDEX_HTML.read_text(encoding="utf-8"), content_type="text/html")


async def scan(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
        args = _namespace_from_payload(payload)
        logger.info(f"Starting scan for {len(args.symbols)} symbols: {args.symbols[:3]}")
        scan_output = run_scan(args)
        logger.info(f"Scan completed: {scan_output.get('status')}")
        body = _scan_response_body(scan_output)
        metadata = build_scan_metadata(scan_output.get("scan_mode") or payload.get("scan_mode", "standard"), scan_output.get("pipeline_stage") or payload.get("pipeline_stage"))
        body.update(metadata)
        body["scan_params"] = payload

        scan_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        body["scan_id"] = scan_id
        _persist_scan_run(scan_id, body)
        save_scan(body, scan_id=scan_id)
        body["archive_scan_id"] = scan_id
        _persist_scan_run(scan_id, body)
        body["saved_scans"] = _db_first_list_scans(limit=20)
        body["comparison"] = _compare_with_previous(body)
        try:
            if getattr(args, "notify_telegram", False):
                dispatch_scan_telegram(scan_output, args)
        except Exception as exc:
            logger.error(f"Telegram dispatch failed for UI scan: {exc}", exc_info=True)
        return web.json_response(body, dumps=lambda value: json.dumps(value, default=str))
    except Exception as e:
        logger.error(f"Scan endpoint error: {e}", exc_info=True)
        return web.json_response({
            "status": "error",
            "message": f"Scan failed: {str(e)}",
            "results": [],
            "ranked": [],
            "breadth": {},
        }, status=500)


async def scans(_: web.Request) -> web.Response:
    return web.json_response({"scans": _db_first_list_scans(limit=40)})


async def scan_detail(request: web.Request) -> web.Response:
    scan_id = request.match_info["scan_id"]
    payload = _db_first_load_scan(scan_id)
    if not payload:
        raise web.HTTPNotFound(text="Scan not found")
    payload["saved_scans"] = _db_first_list_scans(limit=20)
    payload["comparison"] = _compare_with_previous(payload)
    return web.json_response(payload, dumps=lambda value: json.dumps(value, default=str))


async def report_excel(request: web.Request) -> web.Response:
    scan_id = request.match_info["scan_id"]
    payload = _db_first_load_scan(scan_id)
    if not payload:
        raise web.HTTPNotFound(text="Scan not found")

    report_path = payload.get("report_path")
    if not report_path:
        raise web.HTTPNotFound(text="Report file not recorded for scan")

    path = (PROJECT_ROOT / report_path).resolve()
    reports_dir = (PROJECT_ROOT / "reports" / "output").resolve()
    if not str(path).startswith(str(reports_dir)) or not path.exists():
        raise web.HTTPNotFound(text="Report file not found")

    return web.FileResponse(
        path,
        headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
    )


async def history(request: web.Request) -> web.Response:
    stock = request.query.get("stock", "").strip().upper()
    if not stock:
        return web.json_response({"history": []})
    return web.json_response({"history": stock_history(stock, limit=30)})


async def get_settings(request: web.Request) -> web.Response:
    settings = load_settings()
    return web.json_response({"settings": settings}, dumps=lambda value: json.dumps(value, default=str))


async def save_settings_endpoint(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
        save_settings(payload)
        return web.json_response({"status": "ok", "settings": payload}, dumps=lambda value: json.dumps(value, default=str))
    except Exception as e:
        logger.error(f"Settings save failed: {e}", exc_info=True)
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def get_watchlist_order(request: web.Request) -> web.Response:
    settings = load_settings()
    return web.json_response({"watchlist_order": settings.get("watchlist_order", [])}, dumps=lambda value: json.dumps(value, default=str))


async def save_watchlist_order(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
        order = payload.get("order")
        if not isinstance(order, list):
            raise ValueError("order must be an array")
        settings = load_settings()
        settings["watchlist_order"] = order
        save_settings(settings)
        return web.json_response({"status": "ok", "watchlist_order": order}, dumps=lambda value: json.dumps(value, default=str))
    except Exception as e:
        logger.error(f"Watchlist order save failed: {e}", exc_info=True)
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def strategies(request: web.Request) -> web.Response:
    return web.json_response({"strategies": list_strategies(limit=50)}, dumps=lambda value: json.dumps(value, default=str))


async def strategy_detail(request: web.Request) -> web.Response:
    strategy_id = request.match_info.get("strategy_id")
    strategy = load_strategy(strategy_id) if strategy_id else None
    if not strategy:
        raise web.HTTPNotFound(text="Strategy not found")
    return web.json_response({"strategy": strategy}, dumps=lambda value: json.dumps(value, default=str))


async def save_strategy_endpoint(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
        strategy_id = save_strategy(payload)
        payload["strategy_id"] = strategy_id
        return web.json_response({"status": "ok", "strategy": payload}, dumps=lambda value: json.dumps(value, default=str))
    except Exception as e:
        logger.error(f"Strategy save failed: {e}", exc_info=True)
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def delete_strategy_endpoint(request: web.Request) -> web.Response:
    strategy_id = request.match_info.get("strategy_id")
    if not strategy_id:
        return web.json_response({"status": "error", "message": "strategy_id required"}, status=400)
    deleted = delete_strategy(strategy_id)
    if not deleted:
        raise web.HTTPNotFound(text="Strategy not found")
    return web.json_response({"status": "ok", "strategy_id": strategy_id}, dumps=lambda value: json.dumps(value, default=str))


async def market_open_analysis(request: web.Request) -> web.Response:
    scan_id = request.query.get("scan_id", "").strip()
    symbols_param = request.query.get("symbols", "").strip()
    open_time = request.query.get("open_time", "09:08").strip()
    interval = request.query.get("interval", "1m").strip()

    symbols: list[str] = []
    if scan_id:
        payload = _db_first_load_scan(scan_id)
        if payload:
            symbols = [item.get("stock") for item in payload.get("results", []) if item.get("stock")]

    if symbols_param:
        symbols.extend(
            [symbol.strip() for symbol in symbols_param.replace(",", " ").split() if symbol.strip()]
        )

    normalized_symbols = []
    for symbol in symbols:
        normalized = normalize_symbol(symbol)
        if normalized:
            normalized_symbols.append(normalized)
        else:
            logger.warning(f"Market-open analysis dropped invalid symbol: {symbol}")

    symbols = list(dict.fromkeys(normalized_symbols))
    if not symbols:
        raise web.HTTPBadRequest(text="scan_id or symbols parameter required")

    try:
        analysis = calculate_market_open_analysis(
            symbols,
            open_time=open_time,
            interval=interval,
            workers=5,
        )
        return web.json_response(
            {
                "status": "ok",
                "symbols": symbols,
                "open_time": open_time,
                "interval": interval,
                "analysis": analysis,
            },
            dumps=lambda value: json.dumps(value, default=str),
        )
    except Exception as e:
        logger.error(f"Market open analysis failed: {e}", exc_info=True)
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def candlestick_data(request: web.Request) -> web.Response:
    """
    Return candlestick data for a specific stock for the last N days.
    Query params: stock (required), days (optional, default=30), interval (optional, default=1d)
    """
    from data.market_data import get_stock_data

    stock = request.query.get("stock", "").strip()
    days = request.query.get("days", "30").strip()
    interval = request.query.get("interval", "1d").strip()

    normalized_stock = normalize_symbol(stock)
    if not normalized_stock:
        raise web.HTTPBadRequest(text="stock parameter required or invalid")

    try:
        days = int(days)
        days = max(10, min(days, 365))  # Clamp between 10 and 365
    except ValueError:
        days = 30

    # Map days to period string
    period_map = {
        10: "1mo",
        20: "1mo",
        30: "3mo",
        60: "3mo",
        90: "6mo",
        180: "6mo",
        365: "1y",
    }
    period = period_map.get(min(period_map.keys(), key=lambda x: abs(x - days)), "6mo")

    try:
        df = get_stock_data(normalized_stock, period=period, interval=interval)

        if df.empty:
            return web.json_response({
                "stock": stock,
                "candles": [],
                "error": "No data available for this stock"
            })

        # Get last N rows
        df = df.tail(days).reset_index()

        candles = []
        for _, row in df.iterrows():
            candles.append({
                "date": row.get("Date", row.get("Datetime", "")).isoformat() if hasattr(row.get("Date", row.get("Datetime", "")), "isoformat") else str(row.get("Date", row.get("Datetime", ""))),
                "open": round(float(row.get("Open", 0) or 0), 2),
                "high": round(float(row.get("High", 0) or 0), 2),
                "low": round(float(row.get("Low", 0) or 0), 2),
                "close": round(float(row.get("Close", 0) or 0), 2),
                "volume": int(row.get("Volume", 0) or 0),
            })

        return web.json_response({
            "stock": stock,
            "candles": candles,
            "count": len(candles),
        })
    except Exception as e:
        logger.error(f"Candlestick data fetch failed: {e}")
        return web.json_response({
            "stock": stock,
            "candles": [],
            "error": str(e)
        }, status=500)


async def export_watchlist(request: web.Request) -> web.Response:
    scan_id = request.query.get("scan_id", "").strip()
    horizon = request.query.get("horizon", "intraday").strip().lower()
    payload = _db_first_load_scan(scan_id) if scan_id else None
    if not payload:
        # If no explicit scan_id or the requested scan is missing, use the most recent saved scan.
        scans = _db_first_list_scans(limit=1)
        if scans:
            payload = _db_first_load_scan(scans[0]["scan_id"])
            scan_id = scans[0]["scan_id"]
    if not payload:
        raise web.HTTPNotFound(text="Saved scan not found for export")
    rows = _watchlist_rows(payload, horizon=horizon)
    return _csv_response(rows, f"{horizon}_watchlist_{scan_id or 'latest'}.csv")


async def start_scan(request: web.Request) -> web.Response:
    """Start a background scan and return a scan_id immediately."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    scan_id = uuid.uuid4().hex
    scan_tasks[scan_id] = {
        "task": None,
        "status": "queued",
        "result": None,
        "payload": payload,
        "cancel_requested": False,
        "pause_requested": False,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    queued_metadata = build_scan_metadata(payload.get("scan_mode") or payload.get("type") or "standard", payload.get("pipeline_stage"))
    _persist_scan_run(
        scan_id,
        {
            **queued_metadata,
            "scan_params": payload,
            "created_at": scan_tasks[scan_id]["created_at"],
            "message": "Scan queued",
        },
        status="running",
    )

    # Create background task
    task = asyncio.create_task(_run_scan_in_thread(scan_id, payload))
    scan_tasks[scan_id]["task"] = task
    scan_tasks[scan_id]["status"] = "running"

    return web.json_response({
        "scan_id": scan_id,
        "scan_type": _scan_type_name(payload),
        "display_name": _scan_type_name(payload),
        "status": "running",
    })


def _family_matches(payload: dict[str, Any], family: str) -> bool:
    text = " ".join(
        str(payload.get(key, ""))
        for key in ("scan_family", "scanner_bucket", "pipeline_stage", "scan_mode")
    ).lower()
    if family == "open_confirmation":
        return "open_confirmation" in text or "open-confirmation" in text or "market-open" in text
    return family in text


def _latest_scan_for_family(family: str) -> dict[str, Any] | None:
    try:
        payload = v30_store.latest_scan_for_family(family)
        if payload:
            return payload
    except Exception as exc:
        logger.warning(f"DB-first latest scan lookup failed for {family}: {exc}")
    for item in list_scans(limit=120):
        payload = load_scan(item.get("scan_id", ""))
        if payload and _family_matches(payload, family):
            return payload
    return None


async def run_dedicated_scan(request: web.Request) -> web.Response:
    family = request.match_info.get("family", "")
    mode_map = {
        "premarket": "premarket",
        "open-confirmation": "open-confirmation",
        "intraday": "intraday",
    }
    scan_mode = mode_map.get(family)
    if not scan_mode:
        raise web.HTTPNotFound(text="Unknown scanner family")
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    payload["scan_mode"] = scan_mode
    payload["pipeline_stage"] = scanner_profile(scan_mode).stage
    if scan_mode == "open-confirmation" and not payload.get("symbols"):
        latest_premarket = _latest_scan_for_family("premarket")
        if latest_premarket:
            payload.update(build_open_confirmation_payload(latest_premarket))
    if scan_mode == "intraday" and not payload.get("symbols"):
        latest_open = _latest_scan_for_family("open_confirmation")
        if latest_open:
            payload.update(build_intraday_payload(latest_open))

    scan_id = uuid.uuid4().hex
    scan_tasks[scan_id] = {
        "task": None,
        "status": "queued",
        "result": None,
        "payload": payload,
        "cancel_requested": False,
        "pause_requested": False,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    queued_metadata = build_scan_metadata(payload.get("scan_mode") or payload.get("type") or scan_mode, payload.get("pipeline_stage"))
    _persist_scan_run(
        scan_id,
        {
            **queued_metadata,
            "scan_params": payload,
            "created_at": scan_tasks[scan_id]["created_at"],
            "message": "Scan queued",
        },
        status="running",
    )
    task = asyncio.create_task(_run_scan_in_thread(scan_id, payload))
    scan_tasks[scan_id]["task"] = task
    scan_tasks[scan_id]["status"] = "running"
    return web.json_response({
        "scan_id": scan_id,
        "scan_type": _scan_type_name(payload),
        "display_name": _scan_type_name(payload),
        "status": "running",
        "payload": payload,
    }, dumps=lambda value: json.dumps(value, default=str))


async def dedicated_scan_latest(request: web.Request) -> web.Response:
    family = request.match_info.get("family", "").replace("-", "_")
    payload = _latest_scan_for_family(family)
    if not payload:
        return web.json_response({"status": "empty", "message": f"No {family} scan saved yet", "rows": []})
    payload["saved_scans"] = _db_first_list_scans(limit=20)
    return web.json_response(payload, dumps=lambda value: json.dumps(value, default=str))


async def dedicated_scan_results(request: web.Request) -> web.Response:
    scan_id = request.match_info.get("scan_id")
    payload = _db_first_load_scan(scan_id)
    if not payload:
        raise web.HTTPNotFound(text="Scan not found")
    return web.json_response(payload, dumps=lambda value: json.dumps(value, default=str))


async def pipeline_today(_: web.Request) -> web.Response:
    scans = v30_store.scan_payloads(limit=120)
    if not scans:
        for item in list_scans(limit=120):
            payload = load_scan(item.get("scan_id", ""))
            if payload:
                scans.append(payload)
    return web.json_response(pipeline_snapshot(scans), dumps=lambda value: json.dumps(value, default=str))


async def pipeline_prepare(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    stage = normalize_scan_mode(payload.get("stage"))
    source_scan_id = payload.get("source_scan_id")
    source_payload = _db_first_load_scan(source_scan_id) if source_scan_id else None
    if not source_payload:
        source_payload = _latest_scan_for_family("premarket" if stage == "open-confirmation" else "open_confirmation")
    if not source_payload:
        return web.json_response({"status": "empty", "message": "No source scan found for pipeline stage"}, status=404)
    if stage == "open-confirmation":
        prepared = build_open_confirmation_payload(source_payload, market_open_time=str(payload.get("market_open_time") or "09:08"))
    else:
        prepared = build_intraday_payload(source_payload, interval=str(payload.get("interval") or "5m"))
    return web.json_response({"status": "ok", "payload": prepared}, dumps=lambda value: json.dumps(value, default=str))


async def meta_scanner_run(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    timeframe = str(payload.get("timeframe") or request.query.get("timeframe") or "intraday")
    result = await asyncio.to_thread(build_meta_scan, timeframe)
    result["meta_scan_id"] = _persist_meta_scan(result)
    return web.json_response(result, dumps=lambda value: json.dumps(value, default=str))


async def meta_scanner_latest(request: web.Request) -> web.Response:
    timeframe = str(request.query.get("timeframe") or "intraday")
    result = await asyncio.to_thread(build_meta_scan, timeframe)
    return web.json_response(result, dumps=lambda value: json.dumps(value, default=str))


async def meta_scanner_timeframe(request: web.Request) -> web.Response:
    timeframe = request.match_info.get("timeframe", "intraday")
    result = await asyncio.to_thread(build_meta_scan, timeframe)
    return web.json_response(result, dumps=lambda value: json.dumps(value, default=str))


async def meta_scanner_symbol_details(request: web.Request) -> web.Response:
    symbol = normalize_symbol(request.match_info.get("symbol"))
    if not symbol:
        raise web.HTTPBadRequest(text="valid symbol required")
    result = await asyncio.to_thread(build_meta_scan, str(request.query.get("timeframe") or "intraday"))
    matches = [row for row in result.get("all_results", []) if str(row.get("symbol") or row.get("stock")).upper() == symbol]
    if not matches:
        return web.json_response({"status": "empty", "symbol": symbol, "message": "No meta scanner record found", "rows": []}, status=404)
    return web.json_response({"status": "ok", "symbol": symbol, "details": matches[0]}, dumps=lambda value: json.dumps(value, default=str))


async def meta_scanner_conflicts(_: web.Request) -> web.Response:
    result = await asyncio.to_thread(build_meta_scan, "intraday")
    return web.json_response({"status": "ok", "conflicts": result.get("conflicts", [])}, dumps=lambda value: json.dumps(value, default=str))


async def meta_scanner_agreements(_: web.Request) -> web.Response:
    result = await asyncio.to_thread(build_meta_scan, "intraday")
    return web.json_response({"status": "ok", "agreements": result.get("agreements", [])}, dumps=lambda value: json.dumps(value, default=str))


async def final_decisions_latest(request: web.Request) -> web.Response:
    timeframe = str(request.query.get("timeframe") or "intraday")
    result = await asyncio.to_thread(build_meta_scan, timeframe)
    return web.json_response({
        "status": result.get("status", "ok"),
        "generated_at": result.get("generated_at"),
        "timeframe": timeframe,
        "message": result.get("message"),
        "summary": result.get("summary", {}),
        "decisions": result.get("results", []),
        "rejected": result.get("rejected", []),
    }, dumps=lambda value: json.dumps(value, default=str))


async def ml_predictions_latest(request: web.Request) -> web.Response:
    timeframe = str(request.query.get("timeframe") or "intraday")
    result = await asyncio.to_thread(build_meta_scan, timeframe)
    predictions = [
        {
            "symbol": row.get("symbol"),
            "timeframe": row.get("timeframe"),
            "ml_confidence": row.get("ml_confidence"),
            "ai_confidence": row.get("ai_confidence"),
            "backtest_score": row.get("backtest_score"),
            "risk_score": row.get("risk_score"),
            "meta_score": row.get("meta_score"),
            "final_decision": row.get("final_decision"),
            "reason": row.get("reason_selected") or row.get("reason_rejected"),
            "data_freshness": row.get("data_freshness"),
        }
        for row in result.get("all_results", [])
    ]
    return web.json_response({
        "status": result.get("status", "ok"),
        "generated_at": result.get("generated_at"),
        "timeframe": timeframe,
        "predictions": predictions,
        "summary": result.get("summary", {}),
    }, dumps=lambda value: json.dumps(value, default=str))


async def groww_intraday_source(request: web.Request) -> web.Response:
    try:
        limit = int(request.query.get("limit", "80") or 80)
    except ValueError:
        limit = 80
    limit = max(5, min(limit, 200))
    try:
        payload = await asyncio.to_thread(_fetch_groww_intraday_rows, limit)
        return web.json_response(payload, dumps=lambda value: json.dumps(value, default=str))
    except Exception as exc:
        logger.error(f"Groww intraday source failed: {exc}")
        return web.json_response({
            "status": "error",
            "message": f"Unable to fetch Groww intraday stocks: {exc}",
            "source": "https://groww.in/stocks/intraday",
            "rows": [],
            "symbols": [],
        }, status=502)


async def groww_intraday_analyze(request: web.Request) -> web.Response:
    try:
        payload = await request.json() if request.method == "POST" else {}
    except Exception:
        payload = {}
    try:
        limit = int(payload.get("limit") or request.query.get("limit", "80") or 80)
    except ValueError:
        limit = 80
    limit = max(5, min(limit, 200))
    interval = str(payload.get("interval") or request.query.get("interval") or "5m")
    if interval not in {"1m", "2m", "5m", "15m", "30m", "60m", "1h"}:
        interval = "5m"
    try:
        cache_seconds = int(payload.get("cache_seconds") or request.query.get("cache_seconds") or 90)
    except ValueError:
        cache_seconds = 90
    try:
        workers = int(payload.get("workers") or request.query.get("workers") or 4)
    except ValueError:
        workers = 4

    try:
        source_payload = await asyncio.to_thread(_fetch_groww_intraday_rows, limit)
        symbols = list(dict.fromkeys(str(symbol).upper() for symbol in source_payload.get("symbols", []) if symbol))
        if not symbols:
            return web.json_response(
                {
                    "status": "empty",
                    "message": "Groww source returned no resolved NSE symbols.",
                    "source": source_payload,
                    "rows": [],
                    "all_rows": [],
                    "symbols": [],
                },
                dumps=lambda value: json.dumps(value, default=str),
            )

        analysis = await asyncio.to_thread(
            analyze_intraday_symbols,
            symbols,
            interval,
            "groww",
            max(0, cache_seconds),
            max(1, min(workers, 8)),
        )
        rows = []
        for row in analysis.get("rows") or []:
            normalized = IntradayScannerService.normalize_row(row)
            normalized.update({
                "source": "groww",
                "source_name": "Groww Intraday",
                "source_pipeline_stage": "groww_quick_signal",
                "pipeline_stage": "groww_quick_signal",
            })
            rows.append(normalized)
        all_rows = []
        for row in analysis.get("all_rows") or []:
            normalized = IntradayScannerService.normalize_row(row)
            normalized.update({
                "source": "groww",
                "source_name": "Groww Intraday",
                "source_pipeline_stage": "groww_quick_signal",
                "pipeline_stage": "groww_quick_signal",
            })
            all_rows.append(normalized)

        scan_id = f"groww_intraday_quick_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        body = {
            "status": "ok",
            "message": analysis.get("message") or "Groww intraday quick analysis complete.",
            "scan_mode": IntradayScannerService.scan_type,
            "scan_type": IntradayScannerService.scan_type,
            "scan_family": IntradayScannerService.scan_family,
            "scanner_bucket": IntradayScannerService.scanner_bucket,
            "pipeline_stage": "groww_quick_signal",
            "symbols_scanned": len(symbols),
            "candidates_considered": len(all_rows),
            "summary": {
                "qualified": len(rows),
                "source": "groww",
                "source_count": source_payload.get("count", len(symbols)),
                "resolved_count": source_payload.get("resolved_count", len(symbols)),
                "newly_analyzed": len(analysis.get("analyzed_symbols") or []),
                "served_from_cache": len(analysis.get("cached_symbols") or []),
                "failed": len(analysis.get("failed") or []),
            },
            "ranked": rows,
            "top_25": rows[:25],
            "final_top_10": rows[:10],
            "results": all_rows,
            "scan_params": {
                "source": "groww",
                "limit": limit,
                "interval": interval,
                "cache_seconds": cache_seconds,
                "workers": workers,
                "symbols": symbols,
            },
        }
        _persist_scan_run(scan_id, body)
        return web.json_response(
            {
                **analysis,
                "scan_id": scan_id,
                "rows": rows,
                "all_rows": all_rows,
                "source_count": source_payload.get("count", len(symbols)),
                "resolved_count": source_payload.get("resolved_count", len(symbols)),
                "source_rows": source_payload.get("rows", []),
                "source": "https://groww.in/stocks/intraday",
                "engine": "IntradayScannerService",
            },
            dumps=lambda value: json.dumps(value, default=str),
        )
    except Exception as exc:
        logger.error(f"Groww intraday quick analysis failed: {exc}", exc_info=True)
        return web.json_response(
            {
                "status": "error",
                "message": f"Groww intraday quick analysis failed: {exc}",
                "rows": [],
                "all_rows": [],
            },
            status=502,
            dumps=lambda value: json.dumps(value, default=str),
        )


async def stop_scan(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
        scan_id = payload.get("scan_id")
    except Exception:
        return web.json_response({"status": "error", "message": "scan_id required"}, status=400)

    entry = scan_tasks.get(scan_id)
    if not entry:
        return web.json_response({"status": "error", "message": "scan_id not found"}, status=404)

    entry["cancel_requested"] = True
    # Attempt to cancel asyncio task if possible
    task = entry.get("task")
    if task and not task.done():
        try:
            task.cancel()
            entry["status"] = "cancelled"
            metadata = build_scan_metadata((entry.get("payload") or {}).get("scan_mode") or (entry.get("payload") or {}).get("type") or "standard", (entry.get("payload") or {}).get("pipeline_stage"))
            _persist_scan_run(scan_id, {**metadata, "scan_params": entry.get("payload") or {}, "message": "Scan cancelled"}, status="cancelled")
            return web.json_response({"status": "ok", "message": "cancelled"})
        except Exception:
            entry["status"] = "cancel_requested"
            metadata = build_scan_metadata((entry.get("payload") or {}).get("scan_mode") or (entry.get("payload") or {}).get("type") or "standard", (entry.get("payload") or {}).get("pipeline_stage"))
            _persist_scan_run(scan_id, {**metadata, "scan_params": entry.get("payload") or {}, "message": "Scan cancellation requested"}, status="cancel_requested")
            return web.json_response({"status": "ok", "message": "cancel requested"})

    metadata = build_scan_metadata((entry.get("payload") or {}).get("scan_mode") or (entry.get("payload") or {}).get("type") or "standard", (entry.get("payload") or {}).get("pipeline_stage"))
    _persist_scan_run(scan_id, {**metadata, "scan_params": entry.get("payload") or {}, "message": "Scan already completed"}, status=str(entry.get("status") or "completed"))
    return web.json_response({"status": "ok", "message": "already completed"})


async def stop_all_scans(_: web.Request) -> web.Response:
    stopped = []
    for scan_id, entry in scan_tasks.items():
        if entry.get("status") not in {"queued", "running", "paused", "cancel_requested"}:
            continue
        entry["cancel_requested"] = True
        entry["status"] = "cancelled"
        task = entry.get("task")
        if task and not task.done():
            try:
                task.cancel()
            except Exception:
                entry["status"] = "cancel_requested"
        metadata = build_scan_metadata((entry.get("payload") or {}).get("scan_mode") or (entry.get("payload") or {}).get("type") or "standard", (entry.get("payload") or {}).get("pipeline_stage"))
        _persist_scan_run(scan_id, {**metadata, "scan_params": entry.get("payload") or {}, "message": "Scan cancelled"}, status=str(entry.get("status") or "cancelled"))
        stopped.append(_scan_task_summary(scan_id, entry))
    return web.json_response({
        "status": "ok",
        "stopped_count": len(stopped),
        "stopped": stopped,
    }, dumps=lambda value: json.dumps(value, default=str))


async def pause_scan(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
        scan_id = payload.get("scan_id")
    except Exception:
        return web.json_response({"status": "error", "message": "scan_id required"}, status=400)

    entry = scan_tasks.get(scan_id)
    if not entry:
        return web.json_response({"status": "error", "message": "scan_id not found"}, status=404)
    entry["pause_requested"] = True
    entry["status"] = "paused"
    try:
        v30_store.update_scan_run_status(scan_id, status="paused", message="Scan paused")
    except Exception as exc:
        logger.warning(f"Unable to persist pause state for {scan_id}: {exc}")
    return web.json_response({"status": "ok", "message": "pause requested", "scan_id": scan_id})


async def resume_scan(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
        scan_id = payload.get("scan_id")
    except Exception:
        return web.json_response({"status": "error", "message": "scan_id required"}, status=400)

    entry = scan_tasks.get(scan_id)
    if not entry:
        return web.json_response({"status": "error", "message": "scan_id not found"}, status=404)
    entry["pause_requested"] = False
    if entry.get("status") == "paused":
        entry["status"] = "running"
    try:
        v30_store.update_scan_run_status(scan_id, status=str(entry.get("status") or "running"), message="Scan resumed")
    except Exception as exc:
        logger.warning(f"Unable to persist resume state for {scan_id}: {exc}")
    return web.json_response({"status": "ok", "message": "resumed", "scan_id": scan_id})


async def scan_status(request: web.Request) -> web.Response:
    scan_id = request.match_info.get("scan_id")
    entry = scan_tasks.get(scan_id)
    if not entry:
        # Fallback to saved scans
        payload = _db_first_load_scan(scan_id) if scan_id else None
        if payload:
            return web.json_response({"status": "completed", "result": payload})
        return web.json_response({"status": "error", "message": "scan_id not found"}, status=404)

    status = entry.get("status")
    result = entry.get("result")
    return web.json_response({
        "status": status,
        "result": result,
        "payload": entry.get("payload", {}),
        "created_at": entry.get("created_at"),
        "cancel_requested": entry.get("cancel_requested", False),
        "pause_requested": entry.get("pause_requested", False),
    }, dumps=lambda value: json.dumps(value, default=str))


async def v30_backfill_scans(request: web.Request) -> web.Response:
    try:
        limit = int(request.query.get("limit", "500") or 500)
    except ValueError:
        limit = 500
    result = await asyncio.to_thread(v30_store.backfill_saved_scans, max(1, min(limit, 2000)))
    return web.json_response(result, dumps=lambda value: json.dumps(value, default=str))


def _query_payload(request: web.Request) -> dict[str, Any]:
    return {key: value for key, value in request.query.items()}


def _round_float(value: Any, digits: int = 2, default: float = 0.0) -> float:
    try:
        return round(float(value if value is not None else default), digits)
    except (TypeError, ValueError):
        return default


async def quick_intraday_signal(request: web.Request) -> web.Response:
    symbol = normalize_symbol(request.match_info.get("symbol"))
    if not symbol:
        raise web.HTTPBadRequest(text="valid symbol required")
    interval = request.query.get("interval", "5m")
    if interval not in {"1m", "2m", "5m", "15m", "30m", "60m", "1h"}:
        interval = "5m"
    try:
        payload = await asyncio.to_thread(build_quick_intraday_signal, symbol, interval)
        return web.json_response(payload, dumps=lambda value: json.dumps(value, default=str))
    except Exception as exc:
        logger.warning(f"Quick intraday engine failed for {symbol}: {exc}")
        return web.json_response(
            {
                "status": "error",
                "symbol": symbol,
                "interval": interval,
                "message": str(exc),
                "row": None,
                "data_state": "unavailable",
                "stale": True,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            },
            status=503,
            dumps=lambda value: json.dumps(value, default=str),
        )
    period = "5d" if str(interval).endswith("m") else "30d"
    try:
        quote = get_live_quote(symbol, use_cache=False) or {}
        df = get_stock_data(symbol, period=period, interval=interval)
        if df is None or df.empty:
            raise web.HTTPServiceUnavailable(text=f"intraday data unavailable for {symbol}")
        if hasattr(df.columns, "nlevels") and getattr(df.columns, "nlevels", 1) > 1:
            if symbol in df.columns.get_level_values(0):
                df = df[symbol].copy()
            elif symbol in df.columns.get_level_values(-1):
                df = df.xs(symbol, axis=1, level=-1).copy()
            else:
                df.columns = [
                    column[-1] if isinstance(column, tuple) else column
                    for column in df.columns
                ]

        recent = df.tail(80).copy()
        close = recent["Close"].astype(float)
        high = recent["High"].astype(float)
        low = recent["Low"].astype(float)
        volume = recent["Volume"].astype(float) if "Volume" in recent else close * 0
        ltp = _round_float(quote.get("current_price") or close.iloc[-1])
        previous_close = _round_float(quote.get("previous_close") or close.iloc[-2] if len(close) > 1 else close.iloc[-1])
        day_open = _round_float(quote.get("open") or recent["Open"].astype(float).iloc[-1])
        vwap_denominator = float(volume.tail(30).sum() or 0)
        vwap = (
            float(((high.tail(30) + low.tail(30) + close.tail(30)) / 3 * volume.tail(30)).sum() / vwap_denominator)
            if vwap_denominator
            else float(close.tail(20).mean())
        )
        avg_volume = float(volume.tail(30).mean() or 0)
        current_volume = float(volume.iloc[-1] or 0)
        volume_ratio = current_volume / avg_volume if avg_volume else 1.0
        momentum_pct = ((ltp - float(close.iloc[-6])) / float(close.iloc[-6]) * 100) if len(close) >= 6 and close.iloc[-6] else 0.0
        day_change_pct = ((ltp - previous_close) / previous_close * 100) if previous_close else 0.0
        breakout_level = float(high.tail(20).max())
        support = float(low.tail(20).min())
        atr_proxy = float((high.tail(14) - low.tail(14)).mean() or max(ltp * 0.01, 0.05))
        bullish = ltp >= vwap and momentum_pct >= 0
        breakout = ltp >= breakout_level * 0.998
        score = 50
        score += 16 if bullish else -8
        score += 14 if breakout else 0
        score += min(max(momentum_pct * 3, -12), 18)
        score += min(max((volume_ratio - 1) * 12, -8), 16)
        score += 8 if day_change_pct > 0 else -4
        score = max(0, min(100, score))
        signal = "BUY" if score >= 65 else "WATCH" if score >= 48 else "AVOID"
        entry = ltp if signal != "AVOID" else 0
        stoploss = max(support, entry - (atr_proxy * 1.2)) if entry else 0
        risk = max(entry - stoploss, atr_proxy, 0.01) if entry else 0
        target1 = entry + risk if entry else 0
        target2 = entry + (risk * 2) if entry else 0
        row = {
            "stock": symbol,
            "symbol": symbol,
            "sector": "Intraday",
            "live_price": ltp,
            "last_close": previous_close,
            "open": day_open,
            "high": _round_float(high.iloc[-1]),
            "low": _round_float(low.iloc[-1]),
            "volume": int(current_volume),
            "data_timestamp": datetime.now().isoformat(timespec="seconds"),
            "score": _round_float(score),
            "technical_score": _round_float(score),
            "confidence_pct": _round_float(min(95, max(35, score + (volume_ratio * 5)))),
            "ml_probability": _round_float(min(95, max(30, score + (momentum_pct * 2)))),
            "profitability_score": _round_float(score),
            "quality_score": _round_float(min(100, 45 + volume_ratio * 15 + (10 if bullish else 0))),
            "data_reliability_score": 80,
            "volume_strength": _round_float(volume_ratio * 50),
            "breakout_strength": _round_float(80 if breakout else 35),
            "momentum_score": _round_float(50 + momentum_pct * 5),
            "trend_score": _round_float(70 if bullish else 40),
            "risk_score": _round_float(max(10, min(80, (risk / max(entry, 1)) * 1000 if entry else 70))),
            "signal": signal,
            "trade_type": "BUY" if signal == "BUY" else "WATCH",
            "premarket_action": signal,
            "best_horizon": "Intraday",
            "setup_type": "VWAP breakout" if breakout else "VWAP momentum" if bullish else "Wait for VWAP reclaim",
            "trade_reason": (
                f"{signal}: LTP {ltp}, VWAP {vwap:.2f}, momentum {momentum_pct:.2f}%, "
                f"volume {volume_ratio:.2f}x, day change {day_change_pct:.2f}%"
            ),
            "reason": (
                f"{signal}: LTP {ltp}, VWAP {vwap:.2f}, momentum {momentum_pct:.2f}%, "
                f"volume {volume_ratio:.2f}x"
            ),
            "entry": _round_float(entry),
            "entry_price": _round_float(entry),
            "stoploss": _round_float(stoploss),
            "stop_loss": _round_float(stoploss),
            "target1": _round_float(target1),
            "target2": _round_float(target2),
            "risk_reward": 2 if entry else 0,
            "expected_return": _round_float(((target1 - entry) / entry * 100) if entry else 0),
            "score_breakdown": {
                "vwap_analysis": {"raw_score": _round_float(ltp - vwap), "vwap": _round_float(vwap)},
                "breakout_analysis": {"raw_score": 1 if breakout else 0, "level": _round_float(breakout_level)},
                "volume_analysis": {"raw_score": _round_float(volume_ratio), "avg_volume": int(avg_volume)},
                "momentum_analysis": {"raw_score": _round_float(momentum_pct)},
            },
        }
        return web.json_response({"status": "ok", "row": row}, dumps=lambda value: json.dumps(value, default=str))
    except web.HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Quick intraday signal failed for {symbol}: {exc}")
        raise web.HTTPServiceUnavailable(text=f"quick intraday signal unavailable for {symbol}")


async def v20_dashboard(_: web.Request) -> web.Response:
    try:
        await asyncio.wait_for(asyncio.to_thread(v20_store.refresh_realtime_snapshot), timeout=2.0)
    except asyncio.TimeoutError:
        logger.debug("Dashboard realtime refresh skipped: refresh timeout")
    except Exception as exc:
        logger.warning(f"Dashboard realtime refresh skipped: {exc!r}")
    payload = await asyncio.to_thread(v20_store.dashboard_payload)
    return web.json_response(payload, dumps=lambda value: json.dumps(value, default=str))


async def _cached_realtime_payload(max_age_seconds: float = 2.0) -> dict[str, Any]:
    now_ts = datetime.now().timestamp()
    cached = realtime_snapshot_cache.get("values")
    if cached and now_ts - float(realtime_snapshot_cache.get("updated_at", 0)) < max_age_seconds:
        return cached
    if realtime_snapshot_cache.get("refreshing") and cached:
        return {**cached, "status": cached.get("status") or "stale", "serving_cached": True}
    realtime_snapshot_cache["refreshing"] = True
    try:
        payload = await asyncio.wait_for(asyncio.to_thread(v20_store.realtime_payload), timeout=3.5)
        realtime_snapshot_cache["values"] = payload
        realtime_snapshot_cache["updated_at"] = datetime.now().timestamp()
        return payload
    except Exception as exc:
        if cached:
            stale = {
                **cached,
                "status": "stale",
                "serving_cached": True,
                "message": f"Serving cached realtime snapshot while backend refresh catches up: {exc}",
            }
            realtime_snapshot_cache["values"] = stale
            return stale
        return {
            "status": "stale",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "message": f"Realtime snapshot temporarily unavailable; waiting for first successful cache refresh: {exc!r}",
            "freshness": {"updated_at": "", "age_seconds": None, "stale": True},
            "connection": {"stream": "polling", "websocket": False, "redis": False, "hot_cache": "sqlite+memory"},
            "indices": [],
            "buckets": {},
            "ai_insights": [],
            "events": [],
        }
    finally:
        realtime_snapshot_cache["refreshing"] = False


async def realtime_snapshot(_: web.Request) -> web.Response:
    try:
        payload = await _cached_realtime_payload(max_age_seconds=2.0)
    except Exception as exc:
        logger.debug(f"Realtime snapshot unavailable: {exc!r}")
        payload = {
            "status": "stale",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "message": "Realtime snapshot temporarily unavailable; serving explicit stale state.",
            "freshness": {"updated_at": "", "age_seconds": None, "stale": True},
            "connection": {"stream": "polling", "websocket": False, "redis": False, "hot_cache": "sqlite"},
            "buckets": {},
            "events": [],
        }
    return web.json_response(payload, dumps=lambda value: json.dumps(value, default=str))


async def opportunity_latest(request: web.Request) -> web.Response:
    kind = request.match_info.get("kind", "top")
    try:
        limit = int(request.query.get("limit", str(v30_store.V30_OPPORTUNITY_LIMIT if hasattr(v30_store, "V30_OPPORTUNITY_LIMIT") else 50)) or 50)
    except ValueError:
        limit = 50
    payload = await asyncio.to_thread(v30_store.opportunity_rows, kind, limit)
    if payload.get("status") == "empty":
        try:
            await asyncio.to_thread(v20_store.realtime_payload)
            payload = await asyncio.to_thread(v30_store.opportunity_rows, kind, limit)
        except Exception as exc:
            logger.warning(f"Opportunity refresh unavailable for {kind}: {exc}")
            payload["message"] = "Opportunity cache unavailable; run/refresh a live scan or configure provider."
            payload["error"] = str(exc)
    return web.json_response(payload, dumps=lambda value: json.dumps(value, default=str))


async def opportunity_top(request: web.Request) -> web.Response:
    try:
        limit = int(request.query.get("limit", "50") or 50)
    except ValueError:
        limit = 50
    payload = await asyncio.to_thread(v30_store.opportunity_rows, "top", limit)
    if payload.get("status") == "empty":
        try:
            await asyncio.to_thread(v20_store.realtime_payload)
            payload = await asyncio.to_thread(v30_store.opportunity_rows, "top", limit)
        except Exception as exc:
            logger.warning(f"Top opportunity refresh unavailable: {exc}")
            payload["message"] = "Opportunity cache unavailable; run/refresh a live scan or configure provider."
            payload["error"] = str(exc)
    return web.json_response(payload, dumps=lambda value: json.dumps(value, default=str))


async def v30_stream(request: web.Request) -> web.StreamResponse:
    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
    await response.prepare(request)
    sent = 0
    while True:
        if request.transport is None or request.transport.is_closing():
            break
        try:
            snapshot = await _cached_realtime_payload(max_age_seconds=2.0)
        except Exception as exc:
            snapshot = {
                "status": "stale",
                "message": str(exc),
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "freshness": {"updated_at": "", "age_seconds": None, "stale": True},
                "buckets": {},
            }
        events = [
            {"type": "QUOTE_UPDATED", "payload": {"indices": snapshot.get("indices", []), "freshness": snapshot.get("freshness", {})}},
            {"type": "SCANNER_UPDATED", "payload": {"buckets": snapshot.get("buckets", {}), "freshness": snapshot.get("freshness", {})}},
            {"type": "OPPORTUNITY_UPDATED", "payload": {"buckets": snapshot.get("buckets", {}), "freshness": snapshot.get("freshness", {})}},
            {"type": "AI_SCORE_CHANGED", "payload": {"ai_insights": snapshot.get("ai_insights", []), "freshness": snapshot.get("freshness", {})}},
            {"type": "ML_SCORE_CHANGED", "payload": {"freshness": snapshot.get("freshness", {})}},
            {"type": "META_SCORE_CHANGED", "payload": {"freshness": snapshot.get("freshness", {})}},
        ]
        disconnected = False
        for event in events:
            #await response.write(f"event: {event['type']}\ndata: {json.dumps(event, default=str)}\n\n".encode("utf-8"))
            try:
                await response.write(f"event: {event['type']}\ndata: {json.dumps(event, default=str)}\n\n".encode("utf-8"))
            except ClientConnectionResetError:
                logger.debug("Realtime stream client disconnected")
                disconnected = True
                break
            except ConnectionResetError:
                logger.debug("Realtime stream connection reset by peer")
                disconnected = True
                break
        if disconnected:
            break
        sent += 1
        if V30_STREAM_MAX_EVENTS and sent >= V30_STREAM_MAX_EVENTS:
            break
        await asyncio.sleep(max(0.5, float(V30_STREAM_INTERVAL_SECONDS)))
    return response


async def dashboard_live(_: web.Request) -> web.Response:
    try:
        payload = await asyncio.to_thread(v20_store.dashboard_payload)
    except Exception as exc:
        logger.warning(f"Live dashboard unavailable: {exc}")
        return web.json_response(
            {
                "status": "error",
                "data_status": "unavailable",
                "message": "Live dashboard data is unavailable. Check backend data provider and SQLite availability.",
                "error": str(exc),
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            },
            status=503,
        )
    return web.json_response(payload, dumps=lambda value: json.dumps(value, default=str))


async def scanner_latest_alias(request: web.Request) -> web.Response:
    scan_type = str(request.match_info.get("scan_type") or "intraday").strip().lower()
    family_map = {
        "open-confirmation": "open-confirmation",
        "open_confirmation": "open-confirmation",
        "premarket": "premarket",
        "intraday": "intraday",
        "swing": "swing",
        "groww": "groww-intraday",
        "groww-intraday": "groww-intraday",
    }
    family = family_map.get(scan_type, scan_type)
    payload = _latest_scan_for_family(family)
    if not payload and family == "groww-intraday":
        payload = _latest_scan_for_family("intraday")
    if not payload:
        return web.json_response({"status": "empty", "scan_type": scan_type, "message": f"No {scan_type} scan saved yet", "rows": []})
    return web.json_response(payload, dumps=lambda value: json.dumps(value, default=str))


async def v20_stocks(request: web.Request) -> web.Response:
    v20_store.refresh_realtime_snapshot()
    filters = _query_payload(request)
    return web.json_response({"stocks": v20_store.stock_query(filters), "filters": filters}, dumps=lambda value: json.dumps(value, default=str))


async def v20_indices(_: web.Request) -> web.Response:
    v20_store.refresh_realtime_snapshot()
    return web.json_response({"indices": v20_store.rows("SELECT symbol, name, value, change_pct, updated_at FROM market_indices ORDER BY id")})


async def v20_news(_: web.Request) -> web.Response:
    return web.json_response({"news": v20_store.rows("SELECT id, title, category, source, url, published_at FROM news_articles ORDER BY published_at DESC LIMIT 50")})


async def v20_quote(request: web.Request) -> web.Response:
    symbol = normalize_symbol(request.match_info.get("symbol"))
    if not symbol:
        raise web.HTTPBadRequest(text="valid symbol required")
    quote = get_market_data_provider().get_quote(symbol, use_cache=False)
    if not quote:
        raise web.HTTPServiceUnavailable(text=f"live quote unavailable for {symbol}")
    return web.json_response({"quote": quote}, dumps=lambda value: json.dumps(value, default=str))


async def v20_candles(request: web.Request) -> web.Response:
    symbol = normalize_symbol(request.match_info.get("symbol"))
    if not symbol:
        raise web.HTTPBadRequest(text="valid symbol required")
    period = request.query.get("period", "6mo")
    interval = request.query.get("interval", "1d")
    candles = get_market_data_provider().get_historical_prices(symbol, period=period, interval=interval)
    if not candles:
        raise web.HTTPServiceUnavailable(text=f"historical candles unavailable for {symbol}")
    return web.json_response({"symbol": symbol, "period": period, "interval": interval, "candles": candles}, dumps=lambda value: json.dumps(value, default=str))


async def stock_search(request: web.Request) -> web.Response:
    query = str(request.query.get("q") or "")
    try:
        limit = max(1, min(25, int(request.query.get("limit", "12"))))
    except ValueError:
        limit = 12
    return web.json_response(stock_data_service.search(query, limit), dumps=lambda value: json.dumps(value, default=str))


async def stock_detail(request: web.Request) -> web.Response:
    symbol = normalize_stock_symbol(request.match_info.get("symbol"))
    if not symbol:
        raise web.HTTPBadRequest(text="valid symbol required")
    payload = await stock_data_service.get_stock(symbol)
    status = 503 if payload.get("status") == "error" and not payload.get("stale") else 200
    return web.json_response(payload, status=status, dumps=lambda value: json.dumps(value, default=str))


async def stock_candles(request: web.Request) -> web.Response:
    symbol = normalize_stock_symbol(request.match_info.get("symbol"))
    if not symbol:
        raise web.HTTPBadRequest(text="valid symbol required")
    range_key = str(request.query.get("range") or "1D")
    payload = await stock_data_service.get_candles(symbol, range_key)
    status = 503 if payload.get("status") == "error" and not payload.get("stale") else 200
    return web.json_response(payload, status=status, dumps=lambda value: json.dumps(value, default=str))


async def stock_analysis(request: web.Request) -> web.Response:
    symbol = normalize_stock_symbol(request.match_info.get("symbol"))
    if not symbol:
        raise web.HTTPBadRequest(text="valid symbol required")
    payload = await stock_data_service.get_analysis(symbol)
    payload["scan_type"] = str(request.query.get("scan_type") or "all")
    status = 503 if payload.get("status") == "error" and not payload.get("stale") else 200
    return web.json_response(payload, status=status, dumps=lambda value: json.dumps(value, default=str))


async def stock_stream(request: web.Request) -> web.StreamResponse:
    symbol = normalize_stock_symbol(request.match_info.get("symbol"))
    if not symbol:
        raise web.HTTPBadRequest(text="valid symbol required")
    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
    await response.prepare(request)
    last_quote_signature = ""
    last_analysis_signature = ""
    try:
        for _ in range(1800):
            stock = await stock_data_service.get_stock(symbol, allow_stale=True)
            quote_signature = json.dumps(stock.get("quote") or {}, sort_keys=True, default=str)
            if quote_signature != last_quote_signature:
                await response.write(await encode_sse("QUOTE_UPDATED", stock))
                last_quote_signature = quote_signature
            analysis = await stock_data_service.get_analysis(symbol, allow_stale=True)
            analysis_signature = json.dumps(
                {
                    "intraday": analysis.get("intraday_view"),
                    "swing": analysis.get("swing_view"),
                    "price": (analysis.get("quote") or {}).get("current_price"),
                    "stale": analysis.get("stale"),
                },
                sort_keys=True,
                default=str,
            )
            if analysis_signature != last_analysis_signature:
                await response.write(await encode_sse("ANALYSIS_UPDATED", analysis))
                last_analysis_signature = analysis_signature
            await response.write(await encode_sse("HEARTBEAT", {"symbol": symbol, "updated_at": datetime.now().isoformat(timespec="seconds")}))
            await asyncio.sleep(2)
    except (asyncio.CancelledError, ClientConnectionResetError, ConnectionResetError):
        logger.debug(f"Stock stream client disconnected for {symbol}")
    except Exception as exc:
        logger.warning(f"Stock stream ended for {symbol}: {exc}")
    return response


async def watchlist_items(request: web.Request) -> web.Response:
    if request.method == "GET":
        return web.json_response(
            {"status": "ok", "items": watchlist_monitor.list_items(), "settings": watchlist_monitor.get_settings()},
            dumps=lambda value: json.dumps(value, default=str),
        )
    payload = await request.json()
    try:
        item = await watchlist_monitor.add_item(payload)
    except ValueError as exc:
        return web.json_response({"status": "error", "message": str(exc)}, status=400)
    return web.json_response({"status": "ok", "item": item}, dumps=lambda value: json.dumps(value, default=str))


async def watchlist_item_update(request: web.Request) -> web.Response:
    symbol = normalize_stock_symbol(request.match_info.get("symbol"))
    if not symbol:
        raise web.HTTPBadRequest(text="valid symbol required")
    if request.method == "DELETE":
        removed = watchlist_monitor.remove_item(symbol)
        return web.json_response({"status": "ok", "removed": removed, "symbol": symbol})
    payload = await request.json()
    item = await watchlist_monitor.update_item(symbol, payload)
    return web.json_response({"status": "ok", "item": item}, dumps=lambda value: json.dumps(value, default=str))


async def watchlist_status(_: web.Request) -> web.Response:
    return web.json_response(
        {"status": "ok", "monitor": watchlist_monitor.status, "count": len(watchlist_monitor.items)},
        dumps=lambda value: json.dumps(value, default=str),
    )


async def watchlist_stream(request: web.Request) -> web.StreamResponse:
    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
    await response.prepare(request)
    last_signature = ""
    try:
        for _ in range(1800):
            payload = {
                "status": "ok",
                "items": watchlist_monitor.list_items(),
                "monitor": watchlist_monitor.status,
                "alerts": watchlist_monitor.alert_history(limit=20),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            signature = json.dumps(payload, sort_keys=True, default=str)
            if signature != last_signature:
                await response.write(await encode_sse("WATCHLIST_UPDATED", payload))
                last_signature = signature
            await response.write(await encode_sse("HEARTBEAT", {"updated_at": datetime.now().isoformat(timespec="seconds")}))
            await asyncio.sleep(2)
    except (asyncio.CancelledError, ClientConnectionResetError, ConnectionResetError):
        logger.debug("Watchlist stream client disconnected")
    except Exception as exc:
        logger.warning(f"Watchlist stream ended: {exc}")
    return response


async def alert_history_api(request: web.Request) -> web.Response:
    return web.json_response(
        {
            "status": "ok",
            "alerts": watchlist_monitor.alert_history(
                symbol=str(request.query.get("symbol") or ""),
                alert_type=str(request.query.get("alert_type") or ""),
                severity=str(request.query.get("severity") or ""),
                action=str(request.query.get("action") or ""),
                date=str(request.query.get("date") or ""),
                telegram_sent=str(request.query.get("telegram_sent") or ""),
                trade_taken=str(request.query.get("trade_taken") or ""),
                limit=max(1, min(500, int(request.query.get("limit", "200") or 200))),
            ),
        },
        dumps=lambda value: json.dumps(value, default=str),
    )


async def watchlist_history_api(request: web.Request) -> web.Response:
    return await alert_history_api(request)


async def alert_settings_api(request: web.Request) -> web.Response:
    if request.method == "GET":
        return web.json_response({"status": "ok", "settings": watchlist_monitor.get_settings()}, dumps=lambda value: json.dumps(value, default=str))
    payload = await request.json()
    settings = watchlist_monitor.update_settings(payload)
    return web.json_response({"status": "ok", "settings": settings}, dumps=lambda value: json.dumps(value, default=str))


async def alert_test_api(request: web.Request) -> web.Response:
    payload = await request.json() if request.can_read_body else {}
    symbol = normalize_stock_symbol(payload.get("symbol") or "TEST.NS")
    alert = watchlist_monitor._alert(
        symbol,
        str(payload.get("alert_type") or "test_alert"),
        str(payload.get("severity") or "medium"),
        float(payload.get("trigger_price") or 0),
        float(payload.get("breakout_level") or 0),
        str(payload.get("message") or f"Test alert for {symbol}"),
    )
    watchlist_monitor.alerts.append(
        {
            "alert_id": f"test-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            **alert,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "delivery_status": "test",
            "telegram_sent": False,
            "desktop_sent": bool(watchlist_monitor.settings.get("desktop_enabled", True)),
            "user_action": "test",
        }
    )
    watchlist_monitor.persist_alerts()
    return web.json_response({"status": "ok", "alert": watchlist_monitor.alerts[-1]}, dumps=lambda value: json.dumps(value, default=str))


async def stock_trade_plan(request: web.Request) -> web.Response:
    symbol = normalize_symbol(request.match_info.get("symbol"))
    if not symbol:
        raise web.HTTPBadRequest(text="valid symbol required")
    scan_type = str(request.query.get("scan_type") or "intraday")
    return web.json_response(ai_intelligence.generate_trade_plan(symbol, scan_type), dumps=lambda value: json.dumps(value, default=str))


async def ai_insight_alias(request: web.Request) -> web.Response:
    symbol = normalize_symbol(request.match_info.get("symbol"))
    if not symbol:
        raise web.HTTPBadRequest(text="valid symbol required")
    scan_type = str(request.query.get("scan_type") or "intraday")
    return web.json_response(ai_intelligence.generate_stock_insight(symbol, scan_type), dumps=lambda value: json.dumps(value, default=str))


async def ml_prediction_symbol(request: web.Request) -> web.Response:
    symbol = normalize_symbol(request.match_info.get("symbol"))
    if not symbol:
        raise web.HTTPBadRequest(text="valid symbol required")
    timeframe = str(request.query.get("timeframe") or "intraday")
    result = await asyncio.to_thread(build_meta_scan, timeframe)
    matches = [
        row for row in result.get("all_results", [])
        if str(row.get("symbol") or row.get("stock") or "").upper() == symbol
    ]
    if not matches:
        return web.json_response(
            {
                "status": "empty",
                "symbol": symbol,
                "timeframe": timeframe,
                "message": "No ML/meta prediction exists for this symbol in latest scan cache.",
            },
            status=404,
        )
    row = matches[0]
    return web.json_response(
        {
            "status": "ok",
            "symbol": symbol,
            "timeframe": timeframe,
            "prediction": {
                "ml_confidence": row.get("ml_confidence"),
                "ai_confidence": row.get("ai_confidence"),
                "backtest_score": row.get("backtest_score"),
                "risk_score": row.get("risk_score"),
                "meta_score": row.get("meta_score"),
                "final_decision": row.get("final_decision"),
                "reason": row.get("reason_selected") or row.get("reason_rejected") or row.get("reason"),
                "data_freshness": row.get("data_freshness"),
            },
            "generated_at": result.get("generated_at"),
        },
        dumps=lambda value: json.dumps(value, default=str),
    )


async def v20_watchlist(request: web.Request) -> web.Response:
    if request.method == "GET":
        return web.json_response({
            "items": v20_store.rows(
                """
                SELECT wi.id, s.symbol, s.name, s.sector, ps.final_ai_score
                FROM watchlist_items wi
                JOIN stocks s ON s.id = wi.stock_id
                JOIN profitability_scores ps ON ps.stock_id = s.id
                WHERE wi.watchlist_id = 1
                  AND wi.created_at >= ?
                ORDER BY ps.final_ai_score DESC
                """,
                (v20_store.user_data_cutoff(),),
            )
        }, dumps=lambda value: json.dumps(value, default=str))

    payload = await request.json()
    symbol = normalize_symbol(payload.get("symbol"))
    if not symbol:
        raise web.HTTPBadRequest(text="symbol required")
    stock = v20_store.rows("SELECT id FROM stocks WHERE symbol=?", (symbol,))
    if not stock:
        raise web.HTTPNotFound(text="stock not found")
    result = v20_store.execute(
        "INSERT OR IGNORE INTO watchlist_items(watchlist_id, stock_id, created_at, updated_at) VALUES(1, ?, ?, ?)",
        (stock[0]["id"], datetime.now().isoformat(timespec="seconds"), datetime.now().isoformat(timespec="seconds")),
    )
    return web.json_response({"status": "ok", **result})


async def v20_alerts(request: web.Request) -> web.Response:
    if request.method == "GET":
        return web.json_response({"alerts": v20_store.rows("SELECT * FROM alerts WHERE created_at >= ? ORDER BY created_at DESC LIMIT 100", (v20_store.user_data_cutoff(),))}, dumps=lambda value: json.dumps(value, default=str))
    payload = await request.json()
    symbol = normalize_symbol(payload.get("symbol"))
    stock_id = None
    if symbol:
        stock = v20_store.rows("SELECT id FROM stocks WHERE symbol=?", (symbol,))
        stock_id = stock[0]["id"] if stock else None
    timestamp = datetime.now().isoformat(timespec="seconds")
    result = v20_store.execute(
        "INSERT INTO alerts(user_id, stock_id, alert_type, condition, threshold, active, created_at, updated_at) VALUES(1, ?, ?, ?, ?, 1, ?, ?)",
        (
            stock_id,
            payload.get("alert_type", "price"),
            payload.get("condition", "above"),
            float(payload.get("threshold", 0) or 0),
            timestamp,
            timestamp,
        ),
    )
    return web.json_response({"status": "ok", **result})


async def telegram_stock_alert(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
        symbol = normalize_symbol(payload.get("symbol"))
        if not symbol:
            raise web.HTTPBadRequest(text="symbol is required")
        category = payload.get("telegram_category") or payload.get("category") or "Intraday"
        quote = get_live_quote(symbol, use_cache=False) or {}
        live_price = payload.get("live_price") or quote.get("current_price") or quote.get("regularMarketPrice") or quote.get("last_close") or "-"
        entry = payload.get("entry_price") or payload.get("entry") or "-"
        stop = payload.get("stop_loss") or payload.get("stoploss") or "-"
        target1 = payload.get("target1") or payload.get("target_1") or "-"
        target2 = payload.get("target2") or payload.get("target_2") or "-"
        status = payload.get("status") or "Price alert"
        message = "\n".join([
            f"{status}: {symbol}",
            f"LTP: {live_price}",
            f"Entry: {entry}",
            f"Stoploss: {stop}",
            f"Target 1: {target1}",
            f"Target 2: {target2}",
            f"Time: {datetime.now().isoformat(timespec='seconds')}",
        ])
        result = send_telegram_messages(category, message)
        return web.json_response({"status": "ok", "symbol": symbol, "telegram_category": category, "telegram": result})
    except web.HTTPException:
        raise
    except TelegramDeliveryError as exc:
        logger.warning(f"Telegram stock alert failed: {exc}")
        return web.json_response({"status": "error", "message": str(exc)}, status=503)
    except Exception as exc:
        logger.error(f"Telegram stock alert failed: {exc}", exc_info=True)
        return web.json_response({"status": "error", "message": str(exc)}, status=500)


async def telegram_status(request: web.Request) -> web.Response:
    category = request.query.get("category", "Intraday")
    return web.json_response({"status": "ok", "telegram": telegram_config_status(category)})


async def telegram_test(request: web.Request) -> web.Response:
    try:
      payload = await request.json()
    except Exception:
      payload = {}
    category = payload.get("telegram_category") or payload.get("category") or "Intraday"
    message = payload.get("message") or f"Scanner Telegram test: {datetime.now().isoformat(timespec='seconds')}"
    try:
        result = send_telegram_messages(category, message)
        return web.json_response({"status": "ok", "telegram": result})
    except TelegramDeliveryError as exc:
        logger.warning(f"Telegram test failed: {exc}")
        return web.json_response({"status": "error", "message": str(exc), "telegram": telegram_config_status(category)}, status=503)


async def v20_portfolio(_: web.Request) -> web.Response:
    return web.json_response({
        "portfolio": v20_store.rows(
            """
            SELECT ph.id, s.symbol, s.name, ph.quantity, ph.average_price, latest.price AS live_price,
              ROUND((latest.price - ph.average_price) * ph.quantity, 2) AS unrealized_pnl
            FROM portfolio_holdings ph
            JOIN stocks s ON s.id = ph.stock_id
            JOIN (
              SELECT sp1.* FROM stock_prices sp1
              JOIN (SELECT stock_id, MAX(id) AS max_id FROM stock_prices GROUP BY stock_id) x ON x.max_id = sp1.id
            ) latest ON latest.stock_id = s.id
            WHERE ph.portfolio_id = 1
              AND ph.created_at >= ?
            """,
            (v20_store.user_data_cutoff(),),
        )
    }, dumps=lambda value: json.dumps(value, default=str))


async def v20_reports(_: web.Request) -> web.Response:
    return web.json_response({"reports": v20_store.rows("SELECT * FROM reports ORDER BY created_at DESC LIMIT 100")}, dumps=lambda value: json.dumps(value, default=str))


async def v20_backtests(request: web.Request) -> web.Response:
    if request.method == "GET":
        return web.json_response({"backtests": v20_store.rows("SELECT * FROM backtests ORDER BY created_at DESC LIMIT 100")}, dumps=lambda value: json.dumps(value, default=str))
    payload = await request.json()
    timestamp = datetime.now().isoformat(timespec="seconds")
    result = v20_store.execute(
        "INSERT INTO backtests(user_id, name, strategy, win_rate, profit_factor, max_drawdown, created_at, updated_at) VALUES(1, ?, ?, ?, ?, ?, ?, ?)",
        (
            payload.get("name", "V20 Backtest"),
            json.dumps(payload.get("strategy", payload), default=str),
            float(payload.get("win_rate", 0) or 0),
            float(payload.get("profit_factor", 0) or 0),
            float(payload.get("max_drawdown", 0) or 0),
            timestamp,
            timestamp,
        ),
    )
    return web.json_response({"status": "ok", **result})


async def v20_paper_trades(request: web.Request) -> web.Response:
    if request.method == "GET":
        return web.json_response({"trades": v20_store.rows("SELECT * FROM paper_trades WHERE created_at >= ? ORDER BY created_at DESC LIMIT 100", (v20_store.user_data_cutoff(),))}, dumps=lambda value: json.dumps(value, default=str))
    payload = await request.json()
    symbol = normalize_symbol(payload.get("symbol"))
    stock = v20_store.rows("SELECT id FROM stocks WHERE symbol=?", (symbol,)) if symbol else []
    if not stock:
        raise web.HTTPBadRequest(text="valid symbol required")
    timestamp = datetime.now().isoformat(timespec="seconds")
    result = v20_store.execute(
        "INSERT INTO paper_trades(user_id, stock_id, side, quantity, entry_price, status, created_at, updated_at) VALUES(1, ?, ?, ?, ?, 'open', ?, ?)",
        (stock[0]["id"], payload.get("side", "BUY"), float(payload.get("quantity", 1) or 1), float(payload.get("entry_price", 0) or 0), timestamp, timestamp),
    )
    return web.json_response({"status": "ok", **result})


async def v20_user_settings(request: web.Request) -> web.Response:
    if request.method == "GET":
        settings = v20_store.rows("SELECT * FROM user_settings WHERE user_id=1")
        return web.json_response({"settings": settings[0] if settings else {}})
    payload = await request.json()
    timestamp = datetime.now().isoformat(timespec="seconds")
    v20_store.execute(
        """
        INSERT INTO user_settings(user_id, theme, density, notifications_enabled, created_at, updated_at)
        VALUES(1, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET theme=excluded.theme, density=excluded.density,
          notifications_enabled=excluded.notifications_enabled, updated_at=excluded.updated_at
        """,
        (payload.get("theme", "quantum"), payload.get("density", "analyst"), 1 if payload.get("notifications_enabled", True) else 0, timestamp, timestamp),
    )
    return web.json_response({"status": "ok"})


async def v20_saved_scanners(request: web.Request) -> web.Response:
    if request.method == "GET":
        return web.json_response({"saved_scanners": v20_store.rows("SELECT * FROM saved_scanners ORDER BY created_at DESC")}, dumps=lambda value: json.dumps(value, default=str))
    payload = await request.json()
    timestamp = datetime.now().isoformat(timespec="seconds")
    result = v20_store.execute(
        "INSERT INTO saved_scanners(user_id, name, config_json, created_at, updated_at) VALUES(1, ?, ?, ?, ?)",
        (payload.get("name", "Saved Scanner"), json.dumps(payload.get("config", payload), default=str), timestamp, timestamp),
    )
    return web.json_response({"status": "ok", **result})


async def v20_saved_filters(request: web.Request) -> web.Response:
    if request.method == "GET":
        return web.json_response({"saved_filters": v20_store.rows("SELECT * FROM saved_filters ORDER BY created_at DESC")}, dumps=lambda value: json.dumps(value, default=str))
    payload = await request.json()
    timestamp = datetime.now().isoformat(timespec="seconds")
    result = v20_store.execute(
        "INSERT INTO saved_filters(user_id, name, filter_json, created_at, updated_at) VALUES(1, ?, ?, ?, ?)",
        (payload.get("name", "Saved Filter"), json.dumps(payload.get("filters", payload), default=str), timestamp, timestamp),
    )
    return web.json_response({"status": "ok", **result})


async def ai_market_summary(_: web.Request) -> web.Response:
    return web.json_response(ai_intelligence.market_summary(), dumps=lambda value: json.dumps(value, default=str))


async def ai_stock_insight(request: web.Request) -> web.Response:
    symbol = normalize_symbol(request.match_info.get("symbol", ""))
    scan_type = request.query.get("scan_type", "")
    return web.json_response(ai_intelligence.generate_stock_insight(symbol, scan_type), dumps=lambda value: json.dumps(value, default=str))


async def ai_stock_trade_plan(request: web.Request) -> web.Response:
    symbol = normalize_symbol(request.match_info.get("symbol", ""))
    scan_type = request.query.get("scan_type", "")
    return web.json_response(ai_intelligence.generate_trade_plan(symbol, scan_type), dumps=lambda value: json.dumps(value, default=str))


async def ai_scanner_insights(request: web.Request) -> web.Response:
    scan_type = request.match_info.get("scan_type", "dashboard")
    return web.json_response(ai_intelligence.scanner_insights(scan_type), dumps=lambda value: json.dumps(value, default=str))


async def ai_watchlist_insights(_: web.Request) -> web.Response:
    watch_rows = v20_store.rows(
        """
        SELECT s.symbol FROM watchlist_items wi
        JOIN stocks s ON s.id = wi.stock_id
        WHERE wi.watchlist_id = 1
        ORDER BY wi.created_at DESC LIMIT 12
        """
    )
    insights = [ai_intelligence.generate_stock_insight(row["symbol"], "watchlist") for row in watch_rows]
    return web.json_response({"count": len(insights), "insights": insights}, dumps=lambda value: json.dumps(value, default=str))


async def ai_portfolio_insights(_: web.Request) -> web.Response:
    holdings = v20_store.rows(
        """
        SELECT s.symbol, s.sector, ph.quantity, ph.average_price
        FROM portfolio_holdings ph
        JOIN stocks s ON s.id = ph.stock_id
        WHERE ph.portfolio_id = 1
        """
    )
    if not holdings:
        return web.json_response({
            "summary": "Insufficient data to generate reliable insight.",
            "risks": ["No portfolio holdings are stored."],
            "insights": [],
        })
    insights = [ai_intelligence.generate_stock_insight(row["symbol"], "portfolio") for row in holdings]
    sectors: dict[str, float] = {}
    for row in holdings:
        sectors[row["sector"]] = sectors.get(row["sector"], 0) + float(row.get("quantity") or 0)
    return web.json_response({"summary": f"Portfolio has {len(holdings)} holdings across {len(sectors)} sectors.", "sectorExposure": sectors, "insights": insights}, dumps=lambda value: json.dumps(value, default=str))


async def ai_daily_report(_: web.Request) -> web.Response:
    return web.json_response({"summary": ai_intelligence.market_summary(), "scanner": ai_intelligence.scanner_insights("daily"), "generatedAt": datetime.now().isoformat(timespec="seconds")}, dumps=lambda value: json.dumps(value, default=str))


async def ai_copilot_query(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return web.json_response(ai_intelligence.copilot_query(str(payload.get("query") or "")), dumps=lambda value: json.dumps(value, default=str))


async def ai_insights_refresh(_: web.Request) -> web.Response:
    stocks = v20_store.stock_query({"limit": 20})
    insights = [ai_intelligence.generate_stock_insight(row["symbol"], "refresh") for row in stocks[:10]]
    return web.json_response({"status": "ok", "count": len(insights), "insights": insights}, dumps=lambda value: json.dumps(value, default=str))


async def ai_alert_create(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    symbol = normalize_symbol(payload.get("symbol", ""))
    alert_type = str(payload.get("alert_type") or "ai_rating_changed")
    threshold = float(payload.get("threshold") or 0)
    stock_rows = v20_store.rows("SELECT id FROM stocks WHERE symbol=?", (symbol,))
    if not stock_rows:
        return web.json_response({"status": "error", "message": "symbol not found"}, status=404)
    timestamp = datetime.now().isoformat(timespec="seconds")
    result = v20_store.execute(
        "INSERT INTO alerts(user_id, stock_id, alert_type, condition, threshold, active, created_at, updated_at) VALUES(1, ?, ?, ?, ?, 1, ?, ?)",
        (stock_rows[0]["id"], alert_type, str(payload.get("condition") or "changed"), threshold, timestamp, timestamp),
    )
    return web.json_response({"status": "ok", "symbol": symbol, "alert_type": alert_type, **result})


async def realtime_snapshot_warmer(app: web.Application):
    async def loop() -> None:
        while True:
            try:
                await asyncio.to_thread(v20_store.realtime_payload)
            except Exception as exc:
                logger.warning(f"Realtime snapshot warmer skipped cycle: {exc}")
            await asyncio.sleep(30)

    task = asyncio.create_task(loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def v30_backfill_worker(app: web.Application):
    task = asyncio.create_task(asyncio.to_thread(v30_store.backfill_saved_scans, 500))
    try:
        yield
    finally:
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning(f"V30 background backfill ended with warning: {exc}")


async def stock_data_worker(app: web.Application):
    await stock_data_service.start()
    try:
        yield
    finally:
        await stock_data_service.stop()


async def watchlist_monitor_worker(app: web.Application):
    await watchlist_monitor.start()
    try:
        yield
    finally:
        await watchlist_monitor.stop()


def create_app() -> web.Application:
    @web.middleware
    async def cors_middleware(request: web.Request, handler):
        if request.method == "OPTIONS":
            response = web.Response(status=204)
        else:
            response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = request.headers.get("Origin", "*")
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

    app = web.Application(client_max_size=2 * 1024 * 1024)
    app.middlewares.append(cors_middleware)
    app.cleanup_ctx.append(v30_backfill_worker)
    app.cleanup_ctx.append(realtime_snapshot_warmer)
    app.cleanup_ctx.append(stock_data_worker)
    app.cleanup_ctx.append(watchlist_monitor_worker)
    # Serve static assets (CSS, JS, images) from ui/static/
    app.router.add_static('/static/', path=str(BASE_DIR / 'static'), show_index=False)
    app.router.add_get("/", index)
    app.router.add_get("/api/health", health)
    app.router.add_get("/api/market/widgets", market_widgets)
    app.router.add_get("/api/dashboard/live", dashboard_live)
    app.router.add_get("/api/stream", v30_stream)
    app.router.add_get("/api/opportunities/top", opportunity_top)
    app.router.add_get("/api/opportunities/{kind}", opportunity_latest)
    app.router.add_get("/api/scanners/{scan_type}/latest", scanner_latest_alias)
    app.router.add_get("/api/search", stock_search)
    app.router.add_get("/api/stocks/{symbol}", stock_detail)
    app.router.add_get("/api/stocks/{symbol}/candles", stock_candles)
    app.router.add_get("/api/stocks/{symbol}/stream", stock_stream)
    app.router.add_get("/api/stocks/{symbol}/analysis", stock_analysis)
    app.router.add_get("/api/stocks/{symbol}/trade-plan", stock_trade_plan)
    app.router.add_get("/api/ai/insights/{symbol}", ai_insight_alias)
    app.router.add_get("/api/ml/predictions/{symbol}", ml_prediction_symbol)
    app.router.add_get("/api/watchlist", watchlist_items)
    app.router.add_post("/api/watchlist", watchlist_items)
    app.router.add_put("/api/watchlist/{symbol}", watchlist_item_update)
    app.router.add_delete("/api/watchlist/{symbol}", watchlist_item_update)
    app.router.add_get("/api/watchlist/status", watchlist_status)
    app.router.add_get("/api/watchlist/history", watchlist_history_api)
    app.router.add_get("/api/watchlist/stream", watchlist_stream)
    app.router.add_get("/api/alerts", alert_history_api)
    app.router.add_post("/api/alerts/test", alert_test_api)
    app.router.add_get("/api/alerts/settings", alert_settings_api)
    app.router.add_put("/api/alerts/settings", alert_settings_api)
    app.router.add_post("/api/scan", scan)
    app.router.add_post("/api/scan/start", start_scan)
    app.router.add_post("/api/scans/{family}/run", run_dedicated_scan)
    app.router.add_get("/api/scans/{family}/latest", dedicated_scan_latest)
    app.router.add_get("/api/scans/{family}/{scan_id}/results", dedicated_scan_results)
    app.router.add_get("/api/scans/pipeline/today", pipeline_today)
    app.router.add_post("/api/scans/pipeline/prepare", pipeline_prepare)
    app.router.add_post("/api/meta-scanner/run", meta_scanner_run)
    app.router.add_get("/api/meta-scanner/latest", meta_scanner_latest)
    app.router.add_get("/api/meta-scanner/conflicts", meta_scanner_conflicts)
    app.router.add_get("/api/meta-scanner/agreements", meta_scanner_agreements)
    app.router.add_get("/api/meta-scanner/{symbol}/details", meta_scanner_symbol_details)
    app.router.add_get("/api/meta-scanner/{timeframe}", meta_scanner_timeframe)
    app.router.add_get("/api/final-decisions/latest", final_decisions_latest)
    app.router.add_get("/api/ml/predictions", ml_predictions_latest)
    app.router.add_get("/api/sources/groww/intraday", groww_intraday_source)
    app.router.add_get("/api/sources/groww/intraday/analyze", groww_intraday_analyze)
    app.router.add_post("/api/sources/groww/intraday/analyze", groww_intraday_analyze)
    app.router.add_post("/api/scan/stop", stop_scan)
    app.router.add_post("/api/scan/stop-all", stop_all_scans)
    app.router.add_post("/api/scan/pause", pause_scan)
    app.router.add_post("/api/scan/resume", resume_scan)
    app.router.add_get("/api/scan/active", active_scan)
    app.router.add_get("/api/scan/active/all", active_scans)
    app.router.add_get("/api/scan/{scan_id}/status", scan_status)
    app.router.add_post("/api/v30/backfill-scans", v30_backfill_scans)
    app.router.add_get("/api/scans", scans)
    app.router.add_get("/api/scans/{scan_id}", scan_detail)
    app.router.add_get("/api/reports/{scan_id}/excel", report_excel)
    app.router.add_get("/api/history", history)
    app.router.add_get("/api/settings", get_settings)
    app.router.add_post("/api/settings", save_settings_endpoint)
    app.router.add_get("/api/watchlist/order", get_watchlist_order)
    app.router.add_post("/api/watchlist/order", save_watchlist_order)
    app.router.add_get("/api/strategies", strategies)
    app.router.add_get("/api/strategies/{strategy_id}", strategy_detail)
    app.router.add_post("/api/strategies", save_strategy_endpoint)
    app.router.add_delete("/api/strategies/{strategy_id}", delete_strategy_endpoint)
    app.router.add_get("/api/market-open-analysis", market_open_analysis)
    app.router.add_get("/api/candlestick", candlestick_data)
    app.router.add_get("/api/export/watchlist", export_watchlist)
    app.router.add_get("/api/intraday/quick-signal/{symbol}", quick_intraday_signal)
    app.router.add_get("/api/realtime/snapshot", realtime_snapshot)
    app.router.add_get("/api/v20/dashboard", v20_dashboard)
    app.router.add_get("/api/v20/stocks", v20_stocks)
    app.router.add_get("/api/v20/indices", v20_indices)
    app.router.add_get("/api/v20/news", v20_news)
    app.router.add_get("/api/v20/quote/{symbol}", v20_quote)
    app.router.add_get("/api/v20/candles/{symbol}", v20_candles)
    app.router.add_get("/api/v20/watchlist", v20_watchlist)
    app.router.add_post("/api/v20/watchlist", v20_watchlist)
    app.router.add_get("/api/v20/alerts", v20_alerts)
    app.router.add_post("/api/v20/alerts", v20_alerts)
    app.router.add_post("/api/telegram/stock-alert", telegram_stock_alert)
    app.router.add_get("/api/telegram/status", telegram_status)
    app.router.add_post("/api/telegram/test", telegram_test)
    app.router.add_get("/api/v20/portfolio", v20_portfolio)
    app.router.add_get("/api/v20/reports", v20_reports)
    app.router.add_get("/api/v20/backtests", v20_backtests)
    app.router.add_post("/api/v20/backtests", v20_backtests)
    app.router.add_get("/api/v20/paper-trades", v20_paper_trades)
    app.router.add_post("/api/v20/paper-trades", v20_paper_trades)
    app.router.add_get("/api/v20/settings", v20_user_settings)
    app.router.add_post("/api/v20/settings", v20_user_settings)
    app.router.add_get("/api/v20/saved-scanners", v20_saved_scanners)
    app.router.add_post("/api/v20/saved-scanners", v20_saved_scanners)
    app.router.add_get("/api/v20/saved-filters", v20_saved_filters)
    app.router.add_post("/api/v20/saved-filters", v20_saved_filters)
    app.router.add_get("/api/ai/market-summary", ai_market_summary)
    app.router.add_get("/api/ai/stock/{symbol}/insight", ai_stock_insight)
    app.router.add_get("/api/ai/stock/{symbol}/trade-plan", ai_stock_trade_plan)
    app.router.add_get("/api/ai/scanner/{scan_type}/insights", ai_scanner_insights)
    app.router.add_get("/api/ai/watchlist/insights", ai_watchlist_insights)
    app.router.add_get("/api/ai/portfolio/insights", ai_portfolio_insights)
    app.router.add_get("/api/ai/reports/daily", ai_daily_report)
    app.router.add_post("/api/ai/copilot/query", ai_copilot_query)
    app.router.add_post("/api/ai/insights/refresh", ai_insights_refresh)
    app.router.add_post("/api/ai/alerts/create", ai_alert_create)
    return app


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", "5000"))
    web.run_app(create_app(), host="127.0.0.1", port=port)
