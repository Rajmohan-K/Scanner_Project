from utils.logger import logger
import numpy as np


def run(df, **kwargs):
    """
    Advanced Volatility Analysis
    """

    try:

        score = 0
        reasons = []

        close = df["Close"]
        high = df["High"]
        low = df["Low"]

        # ==========================
        # Daily Returns Volatility
        # ==========================
        returns = close.pct_change().dropna()

        std_volatility = (
            returns.tail(20).std()
        ) * 100

        # ==========================
        # ATR-like Range
        # ==========================
        ranges = (
            (
                high - low
            ) / close
        ) * 100

        avg_range = ranges.tail(20).mean()

        recent_range = ranges.iloc[-1]

        # ==========================
        # Low Volatility
        # ==========================
        if std_volatility < 1.5:

            score += 10

            reasons.append(
                "Low Stable Volatility"
            )

        elif std_volatility > 4:

            score -= 10

            reasons.append(
                "High Risk Volatility"
            )

        # ==========================
        # Compression
        # ==========================
        if recent_range < avg_range * 0.8:

            score += 15

            reasons.append(
                "Volatility Compression"
            )

        # ==========================
        # Expansion
        # ==========================
        if recent_range > avg_range * 1.5:

            score += 10

            reasons.append(
                "Volatility Expansion"
            )

        # ==========================
        # Extreme Volatility
        # ==========================
        if recent_range > 8:

            score -= 10

            reasons.append(
                "Extreme Candle Volatility"
            )

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "std_volatility": round(
                    std_volatility, 2
                ),
                "avg_range": round(
                    avg_range, 2
                ),
                "recent_range": round(
                    recent_range, 2
                )
            }
        }

    except Exception as e:

        logger.error(
            f"Volatility failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Volatility Error",
            "raw": {}
        }