from utils.logger import logger


DEFAULT_MODEL = {
    "bias": -2.2,
    "weights": {
        "score": 0.030,
        "score_strength": 0.018,
        "confidence": 0.020,
        "profitability": 0.045,
        "win_rate": 0.018,
        "profit_factor": 0.650,
        "drawdown": -0.060,
        "avg_pnl": 0.180,
        "regime_score": 0.050,
        "bullish_modules": 0.070,
        "bearish_modules": 0.020,
        "dominant_modules": 0.050,
    },
}


def load_model():
    """
    Return the current probability model parameters.
    """

    try:
        return DEFAULT_MODEL
    except Exception as exc:
        logger.error(f"Model load failed: {exc}")
        return DEFAULT_MODEL
