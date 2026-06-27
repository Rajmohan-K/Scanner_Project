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
    Convert a broad multi-factor scan into a stricter pre-market decision layer
    evaluating 14 institutional scoring components (0-100).
    """
    try:
        # Extract base metrics
        score = float(result.get("score", 0) or 0)
        confidence = float(result.get("confidence_pct", 0) or 0)
        ml_probability = float(result.get("ml_probability", 0) or 0)
        quality_score = float(result.get("quality_score", 0) or 0)
        profitability_score = float(result.get("profitability_score", 0) or 0)
        risk_reward = float(result.get("risk_reward") or result.get("rrr") or 1.5)
        gap_percent = float(result.get("gap_percent") or result.get("gap_pct") or 0.0)
        risk_level = str(result.get("risk_level", "Unknown") or "Unknown")
        regime = str(result.get("regime", "Unknown") or "Unknown")
        trend_regime = str(result.get("trend_regime", "Unknown") or "Unknown")
        volatility_regime = str(result.get("volatility_regime", "Unknown") or "Unknown")
        trade_type = str(result.get("trade_type", "") or "").upper()
        setup_type = str(result.get("setup_type", "") or "").upper()
        volume_strength = float(result.get("volume_strength") or result.get("relative_volume") or 1.0)
        expected_return = float(result.get("expected_return") or result.get("priority_profit_pct") or 0.0)

        # 1. Gap Quality (0-100)
        abs_gap = abs(gap_percent)
        if 0.5 <= abs_gap <= 3.0:
            gap_quality = 85.0 + ((abs_gap - 0.5) / 2.5) * 15.0
        elif 3.0 < abs_gap <= 5.0:
            gap_quality = 95.0
        elif abs_gap > 5.0:
            gap_quality = 70.0  # Exhaustion risk
        else:
            gap_quality = 40.0 + (abs_gap / 0.5) * 45.0
        gap_quality = _clamp(gap_quality)

        # 2. Volume Confirmation (0-100)
        if volume_strength >= 2.0:
            volume_conf = 95.0
        elif 1.5 <= volume_strength < 2.0:
            volume_conf = 85.0
        elif 1.0 <= volume_strength < 1.5:
            volume_conf = 70.0
        else:
            volume_conf = 40.0 + (volume_strength * 20.0)
        volume_conf = _clamp(volume_conf)

        # 3. Global Market Support (0-100)
        global_score = float(module_results.get("global_sentiment", {}).get("score", 0) or 0)
        # Assuming score is on -10 to +10 range
        global_support = _clamp(50.0 + global_score * 4.0)

        # 4. Index Alignment (0-100)
        bias = "BUY" if ("BUY" in trade_type or "LONG" in setup_type or score > 0) else "SELL" if ("SELL" in trade_type or "SHORT" in setup_type or score < 0) else "HOLD"
        if (trend_regime == "Bullish" and bias == "BUY") or (trend_regime == "Bearish" and bias == "SELL"):
            index_align = 95.0
        elif trend_regime in {"Neutral", "Unknown"}:
            index_align = 65.0
        else:
            index_align = 35.0

        # 5. Sector Strength (0-100)
        sector_score = float(result.get("sector_strength_score") or result.get("sector_score") or module_results.get("sector_analysis", {}).get("score", 0.0) or 0.0)
        sector_strength = _clamp(50.0 + sector_score * 4.0)

        # 6. News Sentiment (0-100)
        stock_news_score = float(module_results.get("news_sentiment", {}).get("score", 0.0) or 0.0)
        market_news_score = float(module_results.get("market_news_sentiment", {}).get("score", 0.0) or 0.0)
        avg_news = (stock_news_score * 0.7) + (market_news_score * 0.3)
        news_sentiment = _clamp(50.0 + avg_news * 40.0)

        # 7. Technical Breakout/Breakdown Setup (0-100)
        tech_score = float(result.get("technical_score") or score or 0.0)
        technical_setup = _clamp(50.0 + tech_score * 2.5)

        # 8. Risk/Reward suitability (0-100)
        if risk_reward >= 2.0:
            rr_suitability = 95.0
        elif 1.8 <= risk_reward < 2.0:
            rr_suitability = 85.0
        elif 1.5 <= risk_reward < 1.8:
            rr_suitability = 70.0
        elif 1.2 <= risk_reward < 1.5:
            rr_suitability = 55.0
        else:
            rr_suitability = 35.0

        # 9. Liquidity (0-100)
        liquidity_score = float(result.get("liquidity_score") or 75.0)
        liquidity = _clamp(liquidity_score)

        # 10. Volatility Suitability (0-100)
        if volatility_regime in {"Normal Vol", "Normal"}:
            volatility_suitability = 90.0
        elif volatility_regime in {"High Vol", "High"}:
            volatility_suitability = 85.0
        elif volatility_regime in {"Extreme Vol", "Extreme"}:
            volatility_suitability = 55.0  # High circuit risk
        elif volatility_regime in {"Low Vol", "Low"}:
            volatility_suitability = 75.0
        else:
            volatility_suitability = 70.0

        # 11. Backtest Success Rate (0-100)
        backtest_win = float(result.get("backtest_win_rate") or result.get("optimized_win_rate") or 0.58)
        if backtest_win > 1.0:
            backtest_win = backtest_win / 100.0
        backtest_success = _clamp(backtest_win * 100.0)

        # 12. ML Probability (0-100)
        ml_prob = ml_probability if ml_probability > 0 else 55.0
        if ml_prob < 1.0:
            ml_prob = ml_prob * 100.0
        ml_score = _clamp(ml_prob)

        # 13. AI Confidence (0-100)
        ai_conf = confidence if confidence > 0 else 60.0
        if ai_conf < 1.0:
            ai_conf = ai_conf * 100.0
        ai_confidence = _clamp(ai_conf)

        # 14. Trap/Exhaustion Risk (0-100; higher means lower risk)
        risk_score = float(result.get("risk_score") or 35.0)
        trap_score = 100.0 - risk_score
        if abs_gap > 5.5:
            trap_score -= 15.0
        if float(result.get("rsi_14", 50)) > 72.0:
            trap_score -= 15.0
        trap_exhaustion = _clamp(trap_score)

        # Calculate final Premarket score as the average of the 14 components
        components = [
            gap_quality, volume_conf, global_support, index_align, sector_strength,
            news_sentiment, technical_setup, rr_suitability, liquidity, volatility_suitability,
            backtest_success, ml_score, ai_confidence, trap_exhaustion
        ]
        premarket_grade = round(sum(components) / len(components), 2)

        # Assign Label based on Premarket Score
        if premarket_grade >= 90.0:
            label = "Premium Trade"
        elif premarket_grade >= 80.0:
            label = "Strong Trade"
        elif premarket_grade >= 70.0:
            label = "Watch Closely"
        elif premarket_grade >= 60.0:
            label = "Weak Setup"
        else:
            label = "Avoid"

        # Check strict Auto-Push criteria
        intraday_ready = (
            premarket_grade >= 80.0 and
            expected_return >= 1.5 and
            risk_reward >= 1.8 and
            liquidity >= 60.0 and
            volume_strength >= 1.2 and
            trap_exhaustion >= 70.0
        )

        swing_ready = (
            premarket_grade >= 80.0 and
            expected_return >= 4.0 and
            risk_reward >= 2.0 and
            trend_regime in {"Bullish", "Strong Uptrend"} and
            quality_score >= 50.0 and
            news_sentiment >= 50.0
        )

        if intraday_ready:
            best_horizon = "Intraday"
            status = "Qualified"
            action = bias
        elif swing_ready:
            best_horizon = "Swing"
            status = "Qualified"
            action = bias
        elif premarket_grade >= 70.0:
            best_horizon = "Watchlist"
            status = "Watch"
            action = "WATCH"
        else:
            best_horizon = "Avoid"
            status = "Avoid"
            action = "AVOID"

        score_breakdown = {
            "gap_quality": round(gap_quality, 1),
            "volume_confirmation": round(volume_conf, 1),
            "global_market_support": round(global_support, 1),
            "index_alignment": round(index_align, 1),
            "sector_strength": round(sector_strength, 1),
            "news_sentiment": round(news_sentiment, 1),
            "technical_setup": round(technical_setup, 1),
            "risk_reward": round(rr_suitability, 1),
            "liquidity": round(liquidity, 1),
            "volatility_suitability": round(volatility_suitability, 1),
            "backtest_success_rate": round(backtest_success, 1),
            "ml_probability": round(ml_score, 1),
            "ai_confidence": round(ai_confidence, 1),
            "trap_exhaustion_risk": round(trap_exhaustion, 1),
        }

        reasons = []
        if label == "Avoid":
            reasons.append("Score below safety threshold")
        if abs_gap > 5.5:
            reasons.append("Gap exhaustion risk")
        if volume_strength < 1.0:
            reasons.append("Weak pre-market volume")
        if trap_exhaustion < 60.0:
            reasons.append("High trap/operator risk")
        if not reasons:
            reasons.append(f"{label} setup with strong core components")

        return {
            "premarket_grade": premarket_grade,
            "premarket_label": label,
            "market_context_score": round(global_support, 2),
            "intraday_ready": intraday_ready,
            "swing_ready": swing_ready,
            "best_horizon": best_horizon,
            "premarket_status": status,
            "premarket_action": action,
            "premarket_reasons": " | ".join(reasons),
            "premarket_score_breakdown": score_breakdown,
        }

    except Exception as exc:
        logger.error(f"Premarket gate failed: {exc}", exc_info=True)
        return {
            "premarket_grade": 0.0,
            "premarket_label": "Avoid",
            "market_context_score": 50.0,
            "intraday_ready": False,
            "swing_ready": False,
            "best_horizon": "Avoid",
            "premarket_status": "Avoid",
            "premarket_action": "AVOID",
            "premarket_reasons": f"Premarket evaluation error: {exc}",
            "premarket_score_breakdown": {},
        }

