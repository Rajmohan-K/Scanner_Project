from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from scanners.final_decision import decide
from ui.storage import list_scans, load_scan
from ui import v30_store


SCAN_WEIGHTS = {
    "premarket": 0.85,
    "open_confirmation": 1.15,
    "intraday": 1.2,
    "swing": 1.0,
    "groww": 0.75,
    "watchlist": 0.55,
    "standard": 0.5,
}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _symbol(row: dict[str, Any]) -> str:
    return str(row.get("stock") or row.get("symbol") or "").strip().upper()


def _family(row: dict[str, Any], payload: dict[str, Any]) -> str:
    text = str(
        row.get("scan_family")
        or row.get("scanner_bucket")
        or row.get("pipeline_stage")
        or row.get("scan_mode")
        or payload.get("scan_family")
        or payload.get("scanner_bucket")
        or payload.get("scan_mode")
        or "standard"
    ).lower().replace("-", "_")
    if "open" in text:
        return "open_confirmation"
    if "premarket" in text:
        return "premarket"
    if "groww" in text:
        return "groww"
    if "intraday" in text:
        return "intraday"
    if "swing" in text:
        return "swing"
    if "watch" in text:
        return "watchlist"
    return "standard"


def _scan_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for key in ("final_top_10", "ranked", "top_25", "filtered_150", "results"):
        value = payload.get(key)
        if not isinstance(value, list):
            continue
        for row in value:
            if not isinstance(row, dict):
                continue
            symbol = _symbol(row)
            if not symbol:
                continue
            dedupe_key = (symbol, key)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            rows.append(row)
    return rows


def _base_score(row: dict[str, Any]) -> float:
    candidates = [
        row.get("final_opportunity_score"),
        row.get("profitability_score"),
        row.get("quality_score"),
        row.get("ml_probability"),
        row.get("confidence_pct"),
        row.get("score"),
    ]
    values = [_float(value) for value in candidates if value not in (None, "")]
    if not values:
        return 0.0
    return max(0.0, min(100.0, sum(values) / len(values)))


def _risk_score(rows: list[dict[str, Any]]) -> float:
    values = [_float(row.get("risk_score")) for row in rows if row.get("risk_score") not in (None, "")]
    return round(sum(values) / len(values), 2) if values else 50.0


def _best_number(rows: list[dict[str, Any]], *keys: str) -> float:
    values = []
    for row in rows:
        for key in keys:
            if row.get(key) not in (None, ""):
                values.append(_float(row.get(key)))
    return round(max(values), 2) if values else 0.0


def _trade_plan(rows: list[dict[str, Any]]) -> dict[str, Any]:
    best = max(rows, key=_base_score)
    return {
        "entry": best.get("entry") or best.get("entry_price") or best.get("entry_zone_low"),
        "stop_loss": best.get("stoploss") or best.get("stop_loss"),
        "target_1": best.get("target1") or best.get("target_1"),
        "target_2": best.get("target2") or best.get("target_2"),
        "target_3": best.get("target3") or best.get("target_3"),
        "risk_reward_ratio": best.get("risk_reward") or best.get("risk_reward_ratio") or best.get("rrr"),
    }


def build_meta_scan(timeframe: str = "intraday", limit_scans: int = 80) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_scan_ids: dict[str, set[str]] = defaultdict(set)
    now = datetime.now().isoformat(timespec="seconds")

    db_rows: list[dict[str, Any]] = []
    try:
        db_rows = v30_store.scanner_results_for_meta(limit_scans=limit_scans)
    except Exception:
        db_rows = []

    if db_rows:
        for row in db_rows:
            symbol = _symbol(row)
            if not symbol:
                continue
            family = _family(row, row)
            grouped[symbol].append({**row, "scan_family": family, "source_scan_id": row.get("source_scan_id")})
            source_scan_ids[symbol].add(str(row.get("source_scan_id") or ""))
    else:
        for summary in list_scans(limit=limit_scans):
            payload = load_scan(summary.get("scan_id", ""))
            if not payload:
                continue
            for row in _scan_rows(payload):
                symbol = _symbol(row)
                if not symbol:
                    continue
                family = _family(row, payload)
                grouped[symbol].append({**row, "scan_family": family, "source_scan_id": payload.get("scan_id")})
                source_scan_ids[symbol].add(str(payload.get("scan_id") or ""))

    results: list[dict[str, Any]] = []
    agreements: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for symbol, rows in grouped.items():
        families = sorted({str(row.get("scan_family") or "standard") for row in rows})
        weighted_scores = []
        for row in rows:
            family = str(row.get("scan_family") or "standard")
            weighted_scores.append(_base_score(row) * SCAN_WEIGHTS.get(family, 0.5))
        scanner_agreement = min(100.0, 35 + len(families) * 15 + max(0, len(rows) - len(families)) * 3)
        signal_strength = min(100.0, sum(weighted_scores) / max(1, len(weighted_scores)))
        ml_confidence = _best_number(rows, "ml_probability", "ml_score", "ml_model_probability")
        ai_confidence = _best_number(rows, "confidence_pct", "overall_confidence", "quality_score")
        backtest_score = _best_number(rows, "backtest_win_rate", "walk_forward_win_rate", "optimized_win_rate")
        if backtest_score <= 1:
            backtest_score *= 100
        risk_score = _risk_score(rows)
        risk_adjusted = max(0.0, signal_strength - max(0.0, risk_score - 45) * 0.65)
        conflict_warnings: list[str] = []
        actions = " ".join(str(row.get("premarket_action") or row.get("action") or row.get("signal") or row.get("trade_type") or "") for row in rows).upper()
        if "BUY" in actions and ("SELL" in actions or "SHORT" in actions):
            conflict_warnings.append("Conflicting buy/sell signals")
        if risk_score > 70:
            conflict_warnings.append("High risk score")
        if ml_confidence and ml_confidence < 50:
            conflict_warnings.append("Weak ML confirmation")
        meta_score = round(
            scanner_agreement * 0.18
            + signal_strength * 0.20
            + ai_confidence * 0.12
            + ml_confidence * 0.15
            + min(100.0, backtest_score) * 0.15
            + risk_adjusted * 0.20,
            2,
        )
        plan = _trade_plan(rows)
        row = {
            "symbol": symbol,
            "stock": symbol,
            "timeframe": timeframe,
            "scan_types_matched": families,
            "source_scan_ids": sorted(source_scan_ids[symbol]),
            "meta_score": meta_score,
            "scanner_agreement_score": round(scanner_agreement, 2),
            "signal_strength_score": round(signal_strength, 2),
            "risk_adjusted_score": round(risk_adjusted, 2),
            "ai_confidence": round(ai_confidence, 2),
            "ml_confidence": round(ml_confidence, 2),
            "risk_score": round(risk_score, 2),
            "backtest_score": round(min(100.0, backtest_score), 2),
            "risk_reward_ratio": plan.get("risk_reward_ratio"),
            "trade_plan": plan,
            "conflict_warnings": conflict_warnings,
            "reason": " | ".join(f"{family} confirmed" for family in families),
            "data_freshness": now,
            "updated_at": now,
        }
        decided = decide(row)
        results.append(decided)
        if len(families) > 1:
            agreements.append({"symbol": symbol, "scan_types": families, "agreement_score": round(scanner_agreement, 2)})
        if conflict_warnings:
            conflicts.append({"symbol": symbol, "warnings": conflict_warnings, "risk_score": round(risk_score, 2)})

    results.sort(key=lambda item: (bool(item.get("should_trade")), _float(item.get("meta_score"))), reverse=True)
    visible = [row for row in results if row.get("should_show")]
    return {
        "status": "ok",
        "generated_at": now,
        "timeframe": timeframe,
        "data_status": "live_scans" if results else "empty",
        "message": "No high-confidence opportunity found." if not visible else f"{len(visible)} decision-ready opportunities.",
        "results": visible,
        "all_results": results,
        "rejected": [row for row in results if not row.get("should_show")],
        "agreements": agreements,
        "conflicts": conflicts,
        "summary": {
            "symbols_analyzed": len(results),
            "shown": len(visible),
            "trade": sum(1 for row in visible if row.get("should_trade")),
            "watch": sum(1 for row in visible if row.get("should_watch")),
            "rejected": sum(1 for row in results if row.get("should_reject")),
        },
    }
