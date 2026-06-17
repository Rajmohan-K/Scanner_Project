from utils.logger import logger


MODULE_WEIGHTS = {

    "breadth_analysis": 1.1,

    "breakout_analysis": 1.5,

    #"candlestick_analysis": 1.0,
    "candlestick_analysis": 1.2,

    "chart_pattern_analysis": 1.1,

    "correlation_analysis": 0.7,

    "delivery_analysis": 1.2,

    "earnings_analysis": 1.1,

    "fibonacci_analysis": 0.8,

    "fundamentals_analysis": 1.0,

    #"gap_analysis": 1.3,
    "gap_analysis": 1.4,

    "insider_activity": 0.9,

    "liquidity_analysis": 1.0,

    "market_structure": 1.4,

    "momentum_analysis": 1.3,

    "options_analysis": 1.2,

    "order_block_analysis": 1.1,

    "pivot_analysis": 0.8,

    "relative_strength": 1.3,

    "seasonality_analysis": 0.6,

    "sector_strength": 1.0,

    "smart_money_analysis": 1.3,

    "support_resistance": 1.1,

    "technical_analysis": 1.2,

    "trend_analysis": 1.4,

    "valuation_analysis": 0.8,

    "volatility_analysis": 1.1,

    "volume_analysis": 1.4,

    #"vwap_analysis": 1.2,
    "vwap_analysis": 1.3,

    "news_sentiment": 0.7,

    "market_news_sentiment": 0.5,

    "global_sentiment": 0.9,

    "fii_dii_analysis": 1.0,

    "war_analysis": 0.8,

    "event_impact_analysis": 1.4
}


def calculate_score(module_results):
    """
    Master Weighted Scoring and Opportunity Classification Engine
    """

    try:
        weighted_score = 0
        raw_score = 0
        total_weight = 0
        breakdown = {}

        by_category = {
            "technical": [
                "technical_analysis",
                "trend_analysis",
                "volatility_analysis",
                "momentum_analysis",
                "breakout_analysis",
                "support_resistance",
                "vwap_analysis",
                "gap_analysis",
            ],
            "volume": [
                "volume_analysis",
                "liquidity_analysis",
                "delivery_analysis",
            ],
            "momentum": [
                "momentum_analysis",
                "relative_strength",
                "trend_analysis",
            ],
            "trend": [
                "trend_analysis",
                "sector_strength",
                "market_structure",
            ],
            "volatility": [
                "volatility_analysis",
            ],
            "market_strength": [
                "breadth_analysis",
                "global_sentiment",
                "fii_dii_analysis",
            ],
            "sector_strength": [
                "sector_strength",
            ],
            "liquidity": [
                "liquidity_analysis",
            ],
            "risk": [
                "gap_analysis",
                "volatility_analysis",
                "market_structure",
            ],
        }

        category_scores = {category: 0.0 for category in by_category}
        category_counts = {category: 0 for category in by_category}

        for module_name, result in module_results.items():
            score = result.get("score", 0)
            weight = MODULE_WEIGHTS.get(module_name, 1.0)
            weighted_value = score * weight

            weighted_score += weighted_value
            raw_score += score
            total_weight += weight

            breakdown[module_name] = {
                "raw_score": score,
                "weight": weight,
                "weighted_score": round(weighted_value, 2),
            }

            for category, modules in by_category.items():
                if module_name in modules:
                    category_scores[category] += score
                    category_counts[category] += 1

        normalized_score = weighted_score / total_weight if total_weight else 0
        normalized_score = max(min(normalized_score, 100), -100)

        category_summary = {}
        for category, total in category_scores.items():
            count = max(category_counts.get(category, 1), 1)
            category_summary[f"{category}_score"] = round(total / count, 2)

        opportunity_score = round(
            max(
                0,
                min(
                    100,
                    normalized_score * 0.45
                    + category_summary.get("technical_score", 0) * 0.15
                    + category_summary.get("volume_score", 0) * 0.12
                    + category_summary.get("momentum_score", 0) * 0.10
                    + category_summary.get("trend_score", 0) * 0.10
                    + category_summary.get("market_strength_score", 0) * 0.05
                    + category_summary.get("sector_strength_score", 0) * 0.04
                    + category_summary.get("liquidity_score", 0) * 0.04
                    - max(0, -category_summary.get("risk_score", 0)) * 0.05
                )
            ),
            2,
        )

        if opportunity_score >= 90:
            classification = "Exceptional Opportunity"
        elif opportunity_score >= 80:
            classification = "High Probability"
        elif opportunity_score >= 70:
            classification = "Good Opportunity"
        elif opportunity_score >= 60:
            classification = "Watchlist"
        else:
            classification = "Ignore"

        return {
            "final_score": round(normalized_score, 2),
            "raw_total": round(raw_score, 2),
            "weighted_total": round(weighted_score, 2),
            "breakdown": breakdown,
            "category_scores": category_summary,
            "final_opportunity_score": opportunity_score,
            "opportunity_classification": classification,
        }

    except Exception as e:
        logger.error(f"Score engine failed: {e}")
        return {
            "final_score": 0,
            "raw_total": 0,
            "weighted_total": 0,
            "breakdown": {},
            "category_scores": {},
            "final_opportunity_score": 0,
            "opportunity_classification": "Ignore",
        }

    except Exception as e:

        logger.error(
            f"Score engine failed: {e}"
        )

        return {
            "final_score": 0,
            "raw_total": 0,
            "weighted_total": 0,
            "breakdown": {}
        }
