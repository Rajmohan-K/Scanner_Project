from __future__ import annotations

from typing import Any

from utils.logger import logger


PROFILE_RULES = {
    "intraday": {
        "min_abs_score": 15,
        "min_confidence": 55,
        "min_ml_probability": 55,
        "min_quality_score": 50,
        "min_profitability_score": 8,
        "min_risk_reward": 1.2,
        "allow_risk_levels": {"Low", "Medium"},
    },
    "swing": {
        "min_abs_score": 12,
        "min_confidence": 52,
        "min_ml_probability": 52,
        "min_quality_score": 52,
        "min_profitability_score": 12,
        "min_risk_reward": 1.5,
        "allow_risk_levels": {"Low", "Medium"},
        "min_profit_factor": 1.0,
    },
}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _passes_profile(result: dict[str, Any], profile: str) -> tuple[bool, list[str]]:
    rules = PROFILE_RULES[profile]
    reasons: list[str] = []

    abs_score = abs(float(result.get("score", 0) or 0))
    confidence = float(result.get("confidence_pct", 0) or 0)
    ml_probability = float(result.get("ml_probability", 0) or 0)
    quality_score = float(result.get("quality_score", 0) or 0)
    profitability_score = float(result.get("profitability_score", 0) or 0)
    risk_reward = float(result.get("risk_reward", 0) or 0)
    risk_level = str(result.get("risk_level", "Unknown") or "Unknown")
    profit_factor = float(result.get("profit_factor", 0) or 0)

    if abs_score < rules["min_abs_score"]:
        reasons.append(f"score<{rules['min_abs_score']}")
    if confidence < rules["min_confidence"]:
        reasons.append(f"confidence<{rules['min_confidence']}")
    if ml_probability < rules["min_ml_probability"]:
        reasons.append(f"ml<{rules['min_ml_probability']}")
    if quality_score < rules["min_quality_score"]:
        reasons.append(f"quality<{rules['min_quality_score']}")
    if profitability_score < rules["min_profitability_score"]:
        reasons.append(f"profitability<{rules['min_profitability_score']}")
    if risk_reward < rules["min_risk_reward"]:
        reasons.append(f"rr<{rules['min_risk_reward']}")
    if risk_level not in rules["allow_risk_levels"]:
        reasons.append(f"risk={risk_level}")
    if "min_profit_factor" in rules and profit_factor < rules["min_profit_factor"]:
        reasons.append(f"pf<{rules['min_profit_factor']}")

    return (len(reasons) == 0, reasons)


def evaluate_premarket_readiness(
    result: dict[str, Any],
    module_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """
    Convert a broad multi-factor scan into a stricter pre-market decision layer.
    """

    try:
        score = float(result.get("score", 0) or 0)
        confidence = float(result.get("confidence_pct", 0) or 0)
        ml_probability = float(result.get("ml_probability", 0) or 0)
        quality_score = float(result.get("quality_score", 0) or 0)
        profitability_score = float(result.get("profitability_score", 0) or 0)
        profit_factor = float(result.get("profit_factor", 0) or 0)
        risk_reward = float(result.get("risk_reward", 0) or 0)
        event_score = float(result.get("event_score", 0) or 0)
        max_drawdown = float(result.get("max_drawdown", 0) or 0)
        gap_percent = abs(float(result.get("gap_percent", 0) or 0))
        risk_level = str(result.get("risk_level", "Unknown") or "Unknown")
        regime = str(result.get("regime", "Unknown") or "Unknown")
        trend_regime = str(result.get("trend_regime", "Unknown") or "Unknown")
        volatility_regime = str(result.get("volatility_regime", "Unknown") or "Unknown")
        trade_type = str(result.get("trade_type", "") or "").upper()
        setup_type = str(result.get("setup_type", "") or "").upper()

        global_score = float(module_results.get("global_sentiment", {}).get("score", 0) or 0)
        market_news_score = float(module_results.get("market_news_sentiment", {}).get("score", 0) or 0)
        stock_news_score = float(module_results.get("news_sentiment", {}).get("score", 0) or 0)
        war_score = float(module_results.get("war_analysis", {}).get("score", 0) or 0)

        context_score = (
            (global_score * 0.40) +
            (market_news_score * 0.18) +
            (stock_news_score * 0.17) +
            (war_score * 0.25)
        )

        risk_penalty = {
            "Low": 0,
            "Medium": 6,
            "High": 16,
            "Unknown": 8,
        }.get(risk_level, 8)

        volatility_penalty = {
            "Low Vol": 0,
            "Normal Vol": 0,
            "High Vol": 4,
            "Extreme Vol": 8,
            "Unknown": 2,
        }.get(volatility_regime, 2)

        premarket_grade = (
            (abs(score) * 0.22) +
            (confidence * 0.17) +
            (ml_probability * 0.24) +
            (quality_score * 0.15) +
            (profitability_score * 0.10) +
            (max(event_score, -20) * 0.25) +
            (profit_factor * 6.0) +
            (risk_reward * 6.5) +
            (context_score * 0.10) -
            (max_drawdown * 0.05) -
            risk_penalty -
            volatility_penalty
        )
        premarket_grade = round(_clamp(premarket_grade), 2)

        intraday_ready, intraday_reasons = _passes_profile(result, "intraday")
        swing_ready, swing_reasons = _passes_profile(result, "swing")

        bias = "BUY" if ("BUY" in trade_type or "LONG" in setup_type or score > 0) else "SELL" if ("SELL" in trade_type or "SHORT" in setup_type or score < 0) else "HOLD"

        if intraday_ready and (gap_percent >= 0.4 or volatility_regime in {"High Vol", "Extreme Vol"}):
            best_horizon = "Intraday"
            status = "Qualified"
            action = bias
        elif swing_ready:
            best_horizon = "Swing"
            status = "Qualified"
            action = bias
        elif premarket_grade >= 55:
            best_horizon = "Watchlist"
            status = "Watchlist"
            action = "WATCH"
        else:
            best_horizon = "Rejected"
            status = "Rejected"
            action = "AVOID"

        reasons: list[str] = []
        if regime not in {"Bullish", "Bearish", "Unknown"}:
            reasons.append(f"regime={regime}")
        if trend_regime and trend_regime != "Unknown":
            reasons.append(trend_regime)
        if volatility_regime and volatility_regime != "Unknown":
            reasons.append(volatility_regime)
        if status != "Qualified":
            reasons.extend(intraday_reasons[:2])
            reasons.extend(swing_reasons[:2])

        return {
            "premarket_grade": premarket_grade,
            "market_context_score": round(context_score, 2),
            "intraday_ready": intraday_ready,
            "swing_ready": swing_ready,
            "best_horizon": best_horizon,
            "premarket_status": status,
            "premarket_action": action,
            "premarket_reasons": " | ".join(dict.fromkeys(reasons)),
        }

    except Exception as exc:
        logger.error(f"Premarket gate failed: {exc}")
        return {
            "premarket_grade": 0.0,
            "market_context_score": 0.0,
            "intraday_ready": False,
            "swing_ready": False,
            "best_horizon": "Rejected",
            "premarket_status": "Rejected",
            "premarket_action": "AVOID",
            "premarket_reasons": "Premarket gate error",
        }
