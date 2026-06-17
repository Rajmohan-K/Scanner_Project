from utils.logger import logger
import numpy as np


def run(df, **kwargs):
    """
    Advanced Chart Pattern Analysis
    Uses live OHLC dataframe.
    """

    try:

        score = 0
        reasons = []

        highs = df["High"].tail(10).tolist()
        lows = df["Low"].tail(10).tolist()
        closes = df["Close"].tail(10).tolist()

        # ==========================
        # Double Bottom Detection
        # ==========================
        sorted_lows = sorted(lows)

        if len(sorted_lows) >= 2:

            low1 = sorted_lows[0]
            low2 = sorted_lows[1]

            if abs(low1 - low2) / low1 < 0.03:

                score += 15
                reasons.append(
                    "Double Bottom"
                )

        # ==========================
        # Double Top Detection
        # ==========================
        sorted_highs = sorted(
            highs,
            reverse=True
        )

        if len(sorted_highs) >= 2:

            high1 = sorted_highs[0]
            high2 = sorted_highs[1]

            if abs(high1 - high2) / high1 < 0.03:

                score -= 15
                reasons.append(
                    "Double Top"
                )

        # ==========================
        # Ascending Triangle
        # ==========================
        if (
            max(highs) - min(highs)
        ) / max(highs) < 0.03:

            if lows[-1] > lows[0]:

                score += 15
                reasons.append(
                    "Ascending Triangle"
                )

        # ==========================
        # Descending Triangle
        # ==========================
        if (
            max(lows) - min(lows)
        ) / min(lows) < 0.03:

            if highs[-1] < highs[0]:

                score -= 15
                reasons.append(
                    "Descending Triangle"
                )

        # ==========================
        # Bull Flag
        # ==========================
        if (
            closes[3] > closes[0] and
            closes[-1] < closes[3] and
            closes[-1] > closes[0]
        ):

            score += 10
            reasons.append(
                "Bull Flag"
            )

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "highs": highs,
                "lows": lows
            }
        }

    except Exception as e:

        logger.error(
            f"Chart Pattern failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Chart Pattern Error",
            "raw": {}
        }