from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from ui import v20_store


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _stock(symbol: str) -> dict[str, Any] | None:
    symbol = str(symbol or "").upper()
    try:
        rows = v20_store.stock_query({"search": symbol, "limit": 20})
    except Exception:
        return None
    exact = [row for row in rows if str(row.get("symbol", "")).upper() == symbol]
    return exact[0] if exact else (rows[0] if rows else None)


def _stock_id(symbol: str) -> int | None:
    try:
        rows = v20_store.rows("SELECT id FROM stocks WHERE symbol=?", (str(symbol).upper(),))
    except Exception:
        return None
    return int(rows[0]["id"]) if rows else None


def _signals(row: dict[str, Any]) -> dict[str, Any]:
    technical = _clamp((_as_float(row.get("technical_score")) or _as_float(row.get("momentum_score")) or _as_float(row.get("final_ai_score"))) * 1.0)
    fundamental = _clamp((
        max(_as_float(row.get("revenue_growth")), 0) * 1.3
        + max(_as_float(row.get("eps_growth")), 0) * 1.2
        + max(_as_float(row.get("roe")), 0)
        + max(_as_float(row.get("roce")), 0) * 0.8
        - max(_as_float(row.get("debt_ratio")) - 1, 0) * 12
    ))
    valuation = _clamp(85 - max(_as_float(row.get("pe")) - 18, 0) * 1.6 - max(_as_float(row.get("debt_ratio")), 0) * 8)
    sector = _clamp(_as_float(row.get("sector_strength_score"), _as_float(row.get("final_ai_score"), 0)))
    risk = _clamp(_as_float(row.get("risk_score"), 50))
    backtest = _clamp(_as_float(row.get("backtest_win_rate"), 0) * 0.75 + _as_float(row.get("profit_factor"), 0) * 12)
    ml = _clamp(_as_float(row.get("ml_probability"), _as_float(row.get("ai_confidence"), _as_float(row.get("final_ai_score"), 0))))
    news = _clamp(_as_float(row.get("news_score"), 50))
    return {
        "technical": round(technical, 2),
        "fundamental": round(fundamental, 2),
        "valuation": round(valuation, 2),
        "sector": round(sector, 2),
        "risk": round(risk, 2),
        "backtest": round(backtest, 2),
        "ml": round(ml, 2),
        "news": round(news, 2),
    }


def _confidence(signals: dict[str, float]) -> float:
    confirmations = [
        signals["technical"] >= 55,
        signals["fundamental"] >= 45,
        signals["valuation"] >= 45,
        signals["ml"] >= 55,
        signals["risk"] <= 60,
        signals["sector"] >= 45,
        signals["backtest"] >= 45,
    ]
    base = (
        signals["technical"] * 0.22
        + signals["fundamental"] * 0.16
        + signals["valuation"] * 0.10
        + signals["ml"] * 0.20
        + signals["sector"] * 0.10
        + max(0, 100 - signals["risk"]) * 0.12
        + signals["backtest"] * 0.10
    )
    if sum(confirmations) < 3:
        base = min(base, 54)
    if sum(confirmations) < 5:
        base = min(base, 74)
    return round(_clamp(base), 2)


def _recommendation(confidence: float, risk: float, signals: dict[str, float]) -> str:
    multi_signal_ok = sum([
        signals["technical"] >= 60,
        signals["fundamental"] >= 50,
        signals["ml"] >= 60,
        signals["sector"] >= 50,
        signals["backtest"] >= 45,
        risk <= 45,
    ])
    if confidence >= 82 and risk <= 45 and multi_signal_ok >= 5:
        return "Strong Buy"
    if confidence >= 68 and risk <= 60 and multi_signal_ok >= 3:
        return "Buy"
    if confidence >= 52:
        return "Watch"
    if risk >= 70:
        return "Avoid"
    return "Hold"


def _reason_list(row: dict[str, Any], signals: dict[str, float]) -> list[str]:
    reasons: list[str] = []
    if signals["technical"] >= 55:
        reasons.append(f"Technical setup is supportive at {signals['technical']:.0f}/100.")
    if signals["ml"] >= 55:
        reasons.append(f"ML confidence is {signals['ml']:.0f}/100 from stored scanner signals.")
    if signals["fundamental"] >= 45:
        reasons.append("Fundamental metrics are acceptable based on growth, ROE/ROCE, and debt.")
    if signals["sector"] >= 50:
        reasons.append("Sector strength is supportive versus the current opportunity universe.")
    if _as_float(row.get("change_pct")) > 0:
        reasons.append(f"Latest live change is positive at {_as_float(row.get('change_pct')):.2f}%.")
    return reasons[:6]


def _risk_list(row: dict[str, Any], signals: dict[str, float]) -> list[str]:
    risks: list[str] = []
    if signals["risk"] >= 60:
        risks.append(f"Risk score is elevated at {signals['risk']:.0f}/100.")
    if signals["backtest"] < 35:
        risks.append("Backtest confirmation is weak or unavailable.")
    if signals["news"] < 45:
        risks.append("News confirmation is missing or not clearly positive.")
    if _as_float(row.get("data_reliability_score")) and _as_float(row.get("data_reliability_score")) < 35:
        risks.append("Data reliability is low, so confidence should be reduced.")
    return risks or ["No major backend risk flag found, but validate live price action before entry."]


def generate_stock_insight(symbol: str, scan_type: str = "") -> dict[str, Any]:
    row = _stock(symbol)
    if not row:
        return {
            "stockSymbol": str(symbol).upper(),
            "scanType": scan_type,
            "recommendation": "Insufficient Data",
            "confidenceScore": 0,
            "riskScore": 100,
            "opportunityScore": 0,
            "summary": "Insufficient data to generate reliable insight.",
            "reasons": [],
            "risks": ["Stock is not available in the latest V20 store."],
            "entryZone": "",
            "stopLoss": None,
            "targets": [],
            "invalidationPoint": "",
            "timeframe": "",
            "dataFreshness": "missing",
            "signalsUsed": [],
            "backtestResult": None,
            "generatedAt": _now(),
        }
    signals = _signals(row)
    confidence = _confidence(signals)
    risk = signals["risk"]
    opportunity = round(_clamp(confidence * 0.65 + signals["technical"] * 0.15 + signals["ml"] * 0.10 + max(0, 100 - risk) * 0.10), 2)
    recommendation = _recommendation(confidence, risk, signals)
    reasons = _reason_list(row, signals)
    risks = _risk_list(row, signals)
    trade_plan = generate_trade_plan(str(row["symbol"]), scan_type, persist=False)
    summary = (
        f"{row['symbol']} is rated {recommendation} with {confidence:.0f}% confidence. "
        f"Opportunity score {opportunity:.0f}/100 uses technical, ML, fundamental, sector, risk, and backtest signals."
    )
    payload = {
        "stockSymbol": row["symbol"],
        "scanType": scan_type or str(row.get("tag") or row.get("best_horizon") or ""),
        "recommendation": recommendation,
        "confidenceScore": confidence,
        "riskScore": risk,
        "opportunityScore": opportunity,
        "summary": summary,
        "reasons": reasons or ["Insufficient confirming reasons from backend signals."],
        "risks": risks,
        "entryZone": trade_plan.get("entryZone", ""),
        "stopLoss": trade_plan.get("stopLoss"),
        "targets": trade_plan.get("targets", []),
        "invalidationPoint": trade_plan.get("invalidationPoint", ""),
        "timeframe": trade_plan.get("timeframe", ""),
        "dataFreshness": str(row.get("last_updated") or row.get("updated_at") or "latest stored snapshot"),
        "signalsUsed": [{"name": key, "score": value} for key, value in signals.items()],
        "backtestResult": {"score": signals["backtest"], "status": "available" if signals["backtest"] else "unavailable"},
        "generatedAt": _now(),
    }
    _persist_insight(payload)
    return payload


def generate_trade_plan(symbol: str, scan_type: str = "", persist: bool = True) -> dict[str, Any]:
    row = _stock(symbol)
    if not row:
        return {"stockSymbol": str(symbol).upper(), "summary": "Insufficient data to generate reliable trade plan.", "targets": []}
    price = _as_float(row.get("live_price"))
    atr_proxy = max(price * 0.012, 0.05)
    risk = _as_float(row.get("risk_score"), 50)
    stop_gap = atr_proxy * (1.4 if risk < 45 else 1.9)
    entry_low = round(max(price - atr_proxy * 0.35, 0), 2)
    entry_high = round(price + atr_proxy * 0.35, 2)
    stop = round(max(price - stop_gap, 0), 2)
    target1 = round(price + stop_gap * 1.5, 2)
    target2 = round(price + stop_gap * 2.4, 2)
    target3 = round(price + stop_gap * 3.2, 2)
    rr = round((target2 - price) / max(price - stop, 0.01), 2)
    signals = _signals(row)
    confidence = _confidence(signals)
    timeframe = "Intraday" if "intraday" in str(scan_type).lower() else "Swing 3-10D" if "swing" in str(scan_type).lower() else str(row.get("tag") or "Active setup")
    payload = {
        "stockSymbol": row["symbol"],
        "scanType": scan_type,
        "tradeType": f"{timeframe} Long" if confidence >= 50 else "Wait",
        "entryZone": f"{entry_low} - {entry_high}",
        "stopLoss": stop,
        "targets": [target1, target2, target3],
        "riskRewardRatio": rr,
        "timeframe": timeframe,
        "setupType": "Momentum/quality setup" if signals["technical"] >= 55 else "Watchlist validation setup",
        "confidence": confidence,
        "reasoning": "Entry is based on latest stored live price, volatility proxy, risk score, and multi-signal confidence.",
        "invalidationPoint": f"Close below {stop} or confidence drops below 50.",
        "generatedAt": _now(),
    }
    if persist:
        _persist_trade_plan(payload)
    return payload


def market_summary() -> dict[str, Any]:
    try:
        dashboard = v20_store.dashboard_payload()
    except Exception as exc:
        return {
            "recommendation": "Insufficient Data",
            "confidenceScore": 0,
            "summary": "Insufficient data to generate reliable insight.",
            "topOpportunities": [],
            "risks": [f"V20 store unavailable: {exc}"],
            "generatedAt": _now(),
        }
    kpis = dashboard.get("kpis") or {}
    breadth = dashboard.get("breadth") or {}
    return {
        "recommendation": kpis.get("market_sentiment") or "Neutral",
        "confidenceScore": kpis.get("market_sentiment_score") or 0,
        "summary": f"Market has {breadth.get('advances', 0)} advances and {breadth.get('declines', 0)} declines from stored live universe.",
        "topOpportunities": dashboard.get("top_opportunities", [])[:5],
        "risks": [dashboard.get("risk", {}).get("label", "Risk unavailable")],
        "generatedAt": _now(),
    }


def scanner_insights(scan_type: str) -> dict[str, Any]:
    try:
        rows = v20_store.stock_query({"limit": 20})
    except Exception as exc:
        return {
            "scanType": scan_type,
            "count": 0,
            "insights": [],
            "summary": "Insufficient data to generate reliable insight.",
            "error": str(exc),
            "generatedAt": _now(),
        }
    filtered = [
        generate_stock_insight(row["symbol"], scan_type)
        for row in rows[:10]
    ]
    return {"scanType": scan_type, "count": len(filtered), "insights": filtered, "generatedAt": _now()}


def copilot_query(query: str) -> dict[str, Any]:
    text = str(query or "").strip()
    if not text:
        return {"answer": "Please ask about a stock, scanner, watchlist, risk, or trade plan.", "data": None}
    upper_tokens = [part.strip("?,. ").upper() for part in text.split()]
    symbol = next((token for token in upper_tokens if token.endswith(".NS") or len(token) <= 12 and token.isalpha()), "")
    if symbol:
        if not symbol.endswith(".NS"):
            symbol = f"{symbol}.NS"
        insight = generate_stock_insight(symbol, "copilot")
        answer = insight["summary"]
        data = insight
    else:
        data = market_summary()
        answer = data["summary"]
    timestamp = _now()
    v20_store.execute(
        "INSERT INTO ai_user_queries(user_id, query, response, context_json, created_at, updated_at) VALUES(1, ?, ?, ?, ?, ?)",
        (text, answer, json.dumps(data, default=str), timestamp, timestamp),
    )
    return {"answer": answer, "data": data, "generatedAt": timestamp}


def _persist_insight(payload: dict[str, Any]) -> None:
    stock_id = _stock_id(payload["stockSymbol"])
    timestamp = payload["generatedAt"]
    v20_store.execute(
        """
        INSERT INTO ai_insights(stock_id, scan_type, insight_type, recommendation, confidence_score, risk_score,
          opportunity_score, summary, reasons_json, risks_json, signals_json, data_freshness, generated_at, created_at, updated_at)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            stock_id,
            payload.get("scanType", ""),
            "stock",
            payload["recommendation"],
            payload["confidenceScore"],
            payload["riskScore"],
            payload["opportunityScore"],
            payload["summary"],
            json.dumps(payload.get("reasons", []), default=str),
            json.dumps(payload.get("risks", []), default=str),
            json.dumps(payload.get("signalsUsed", []), default=str),
            payload.get("dataFreshness", ""),
            timestamp,
            timestamp,
            timestamp,
        ),
    )


def _persist_trade_plan(payload: dict[str, Any]) -> None:
    stock_id = _stock_id(payload["stockSymbol"])
    timestamp = payload["generatedAt"]
    targets = payload.get("targets") or []
    v20_store.execute(
        """
        INSERT INTO ai_trade_plans(stock_id, scan_type, trade_type, entry_zone, stop_loss, target1, target2, target3,
          risk_reward, confidence_score, setup_type, reasoning, invalidation_point, timeframe, generated_at, created_at, updated_at)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            stock_id,
            payload.get("scanType", ""),
            payload.get("tradeType", ""),
            payload.get("entryZone", ""),
            payload.get("stopLoss"),
            targets[0] if len(targets) > 0 else None,
            targets[1] if len(targets) > 1 else None,
            targets[2] if len(targets) > 2 else None,
            payload.get("riskRewardRatio", 0),
            payload.get("confidence", 0),
            payload.get("setupType", ""),
            payload.get("reasoning", ""),
            payload.get("invalidationPoint", ""),
            payload.get("timeframe", ""),
            timestamp,
            timestamp,
            timestamp,
        ),
    )
