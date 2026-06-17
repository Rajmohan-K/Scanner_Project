from utils.logger import logger


def build_feature_vector(
    final_score,
    confidence_pct,
    profitability_score,
    backtest_metrics,
    regime_result,
    module_results,
):
    """
    Create model-ready features from scanner outputs.
    """

    try:
        bullish_count = sum(1 for result in module_results.values() if result.get("score", 0) > 0)
        bearish_count = sum(1 for result in module_results.values() if result.get("score", 0) < 0)
        dominant_count = max(bullish_count, bearish_count)

        return {
            "score": float(final_score),
            "score_strength": abs(float(final_score)),
            "confidence": float(confidence_pct),
            "profitability": float(profitability_score),
            "win_rate": float(backtest_metrics.get("win_rate", 0)),
            "profit_factor": float(backtest_metrics.get("profit_factor", 0)),
            "drawdown": float(backtest_metrics.get("max_drawdown", 0)),
            "avg_pnl": float(backtest_metrics.get("avg_pnl", 0)),
            "regime_score": float(regime_result.get("score", 0)),
            "bullish_modules": float(bullish_count),
            "bearish_modules": float(bearish_count),
            "dominant_modules": float(dominant_count),
        }

    except Exception as exc:
        logger.error(f"Feature engineering failed: {exc}")
        return {
            "score": 0.0,
            "score_strength": 0.0,
            "confidence": 0.0,
            "profitability": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "drawdown": 0.0,
            "avg_pnl": 0.0,
            "regime_score": 0.0,
            "bullish_modules": 0.0,
            "bearish_modules": 0.0,
            "dominant_modules": 0.0,
        }
