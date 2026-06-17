from utils.logger import logger

from regime.trend_regime import detect_trend_regime
from regime.volatility_regime import detect_volatility_regime


def detect_market_regime(df):
    """
    Combine trend and volatility regimes into one regime signal.
    """

    try:
        trend = detect_trend_regime(df)
        volatility = detect_volatility_regime(df)
        total_score = trend.get("score", 0) + volatility.get("score", 0)

        if total_score >= 20:
            label = "Favorable"
        elif total_score >= 5:
            label = "Constructive"
        elif total_score <= -15:
            label = "Hostile"
        elif total_score < 0:
            label = "Fragile"
        else:
            label = "Neutral"

        return {
            "score": total_score,
            "regime": label,
            "trend_regime": trend.get("regime", "Unknown"),
            "volatility_regime": volatility.get("regime", "Unknown"),
            "reason": f"{trend.get('reason', '')}, {volatility.get('reason', '')}".strip(", "),
            "raw": {
                "trend_score": trend.get("score", 0),
                "volatility_score": volatility.get("score", 0),
                "volatility": volatility.get("volatility", 0),
            },
        }

    except Exception as exc:
        logger.error(f"Regime detector failed: {exc}")
        return {
            "score": 0,
            "regime": "Unknown",
            "trend_regime": "Unknown",
            "volatility_regime": "Unknown",
            "reason": "Regime detection error",
            "raw": {},
        }
