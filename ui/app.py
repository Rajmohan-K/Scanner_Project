from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from aiohttp import web


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from main import DEFAULT_BENCHMARK, WATCHLIST, calculate_market_open_analysis, dispatch_scan_telegram, is_valid_symbol, normalize_symbol, run_scan  # noqa: E402
from data.market_data import get_live_quote, get_stock_data  # noqa: E402
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
from ui import v20_store  # noqa: E402
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
    scan_mode = str(payload.get("scan_mode") or payload.get("type") or "")
    if "intraday" in scan_mode and str(interval).lower().endswith(("m", "h")):
        period = "60d" if str(interval).lower().endswith("h") else "30d"

    return argparse.Namespace(
        symbols=symbols,
        period=period,
        interval=interval,
        benchmark=payload.get("benchmark", DEFAULT_BENCHMARK),
        scan_mode=scan_mode,
        top_n=_int_value("top_n", 10),
        workers=_int_value("workers", 5),
        symbols_file=payload.get("symbols_file") or None,
        candidate_pool=_int_value("candidate_pool", 150),
        validation_pool=_int_value("validation_pool", 25),
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
    scans = list_scans(limit=2)
    if len(scans) < 2:
        return {"available": False}

    previous = load_scan(scans[1]["scan_id"])
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


def _scan_type_name(payload: dict[str, Any] | None, fallback: str = "standard") -> str:
    raw = fallback
    if payload:
        raw = str(payload.get("scan_mode") or payload.get("type") or payload.get("scan_type") or fallback)
    return raw.replace("-", " ").replace("_", " ").strip().title() or "Standard Scan"


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
    active_statuses = {"queued", "running", "paused", "cancel_requested"}
    active_entries = [
        (scan_id, entry)
        for scan_id, entry in scan_tasks.items()
        if entry.get("status") in active_statuses
    ]
    if not active_entries:
        return None

    scan_id, entry = sorted(active_entries, key=lambda item: item[1].get("created_at", ""), reverse=True)[0]
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
    }


def _active_scan_list() -> list[dict[str, Any]]:
    rows = [
        _scan_task_summary(scan_id, entry)
        for scan_id, entry in scan_tasks.items()
        if entry.get("status") in {"queued", "running", "paused", "cancel_requested"}
    ]
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
        result = await asyncio.to_thread(run_scan, args)
        # If cancel requested, do not save result as active
        if scan_tasks.get(scan_id, {}).get("cancel_requested"):
            logger.info(f"Background scan {scan_id} completed but was cancelled; discarding results")
            scan_tasks[scan_id]["status"] = "cancelled"
            scan_tasks[scan_id]["result"] = None
            return

        body = _scan_response_body(result)
        body["scan_mode"] = payload.get("scan_mode", "standard")
        body["scan_params"] = payload
        saved_id = save_scan(body)
        body["scan_id"] = saved_id
        body["saved_scans"] = list_scans(limit=20)
        body["comparison"] = _compare_with_previous(body)
        try:
            if getattr(args, "notify_telegram", False):
                dispatch_scan_telegram(result, args)
        except Exception as exc:
            logger.error(f"Telegram dispatch failed for background scan: {exc}", exc_info=True)

        scan_tasks[scan_id]["status"] = "completed"
        scan_tasks[scan_id]["result"] = body
        logger.info(f"Background scan {scan_id} completed and saved as {saved_id}")
    except Exception as e:
        logger.error(f"Background scan {scan_id} failed: {e}", exc_info=True)
        scan_tasks[scan_id]["status"] = "error"
        scan_tasks[scan_id]["result"] = {"status": "error", "message": str(e)}



def _scan_response_body(scan_output: dict[str, Any]) -> dict[str, Any]:
    ranked_df = scan_output.get("ranked")
    ranked_records = []
    if ranked_df is not None and not getattr(ranked_df, "empty", True):
        ranked_records = [
            _serialize_record(record)
            for record in ranked_df.to_dict(orient="records")
        ]

    all_results = [
        _serialize_record(record)
        for record in scan_output.get("results", [])
    ]
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
        return [
            _serialize_record(record)
            for record in scan_output.get(name, [])
            if isinstance(record, dict)
        ]

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

    body = {
        "status": scan_output.get("status", "error"),
        "message": scan_output.get("message", ""),
        "report_path": scan_output.get("report_path"),
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


async def health(_: web.Request) -> web.Response:
    saved_scans = list_scans(limit=1)
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
    if cached_values and not active_scan and now_ts - float(market_widget_cache.get("updated_at", 0)) < 1:
        return web.json_response(cached_values, dumps=lambda value: json.dumps(value, default=str))

    latest_scans = list_scans(limit=1)
    latest_scan = latest_scans[0] if latest_scans else None
    scan_name = active_scan["scan_type"] if active_scan else _scan_type_name(latest_scan, "completed scan")
    scan_status = active_scan["status"] if active_scan else ("completed" if latest_scan else "idle")
    progress = active_scan["progress"] if active_scan else ("100%" if latest_scan else "0%")
    async def _timed_latest_close(symbol: str) -> float | None:
        try:
            return await asyncio.wait_for(asyncio.to_thread(_latest_close, symbol), timeout=4)
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

    scans = list_scans(limit=1)
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
        body["scan_mode"] = payload.get("scan_mode", "standard")
        body["scan_params"] = payload

        scan_id = save_scan(body)
        body["scan_id"] = scan_id
        body["saved_scans"] = list_scans(limit=20)
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
    return web.json_response({"scans": list_scans(limit=40)})


async def scan_detail(request: web.Request) -> web.Response:
    scan_id = request.match_info["scan_id"]
    payload = load_scan(scan_id)
    if not payload:
        raise web.HTTPNotFound(text="Scan not found")
    payload["saved_scans"] = list_scans(limit=20)
    payload["comparison"] = _compare_with_previous(payload)
    return web.json_response(payload, dumps=lambda value: json.dumps(value, default=str))


async def report_excel(request: web.Request) -> web.Response:
    scan_id = request.match_info["scan_id"]
    payload = load_scan(scan_id)
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
        payload = load_scan(scan_id)
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
    payload = load_scan(scan_id) if scan_id else None
    if not payload:
        # If no explicit scan_id or the requested scan is missing, use the most recent saved scan.
        scans = list_scans(limit=1)
        if scans:
            payload = load_scan(scans[0]["scan_id"])
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
            return web.json_response({"status": "ok", "message": "cancelled"})
        except Exception:
            entry["status"] = "cancel_requested"
            return web.json_response({"status": "ok", "message": "cancel requested"})

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
    return web.json_response({"status": "ok", "message": "resumed", "scan_id": scan_id})


async def scan_status(request: web.Request) -> web.Response:
    scan_id = request.match_info.get("scan_id")
    entry = scan_tasks.get(scan_id)
    if not entry:
        # Fallback to saved scans
        payload = load_scan(scan_id) if scan_id else None
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
    v20_store.refresh_realtime_snapshot()
    return web.json_response(v20_store.dashboard_payload(), dumps=lambda value: json.dumps(value, default=str))


async def v20_refresh(_: web.Request) -> web.Response:
    v20_store.refresh_live_store(force=True)
    return web.json_response(v20_store.dashboard_payload(), dumps=lambda value: json.dumps(value, default=str))


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
    # Serve static assets (CSS, JS, images) from ui/static/
    app.router.add_static('/static/', path=str(BASE_DIR / 'static'), show_index=False)
    app.router.add_get("/", index)
    app.router.add_get("/api/health", health)
    app.router.add_get("/api/market/widgets", market_widgets)
    app.router.add_post("/api/scan", scan)
    app.router.add_post("/api/scan/start", start_scan)
    app.router.add_post("/api/scan/stop", stop_scan)
    app.router.add_post("/api/scan/stop-all", stop_all_scans)
    app.router.add_post("/api/scan/pause", pause_scan)
    app.router.add_post("/api/scan/resume", resume_scan)
    app.router.add_get("/api/scan/active", active_scan)
    app.router.add_get("/api/scan/active/all", active_scans)
    app.router.add_get("/api/scan/{scan_id}/status", scan_status)
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
    app.router.add_get("/api/v20/dashboard", v20_dashboard)
    app.router.add_post("/api/v20/refresh", v20_refresh)
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
    return app


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", "5000"))
    web.run_app(create_app(), host="127.0.0.1", port=port)
