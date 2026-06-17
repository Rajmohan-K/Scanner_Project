from utils.logger import logger


def run(df, **kwargs):
    """
    Advanced Market Structure Analysis
    """

    try:

        score = 0
        reasons = []

        highs = df["High"].tail(10).tolist()
        lows = df["Low"].tail(10).tolist()
        closes = df["Close"].tail(10).tolist()

        # ==========================
        # Recent Swing Points
        # ==========================
        recent_high = max(highs[-5:])
        previous_high = max(highs[:5])

        recent_low = min(lows[-5:])
        previous_low = min(lows[:5])

        current_close = closes[-1]

        # ==========================
        # Higher High
        # ==========================
        if recent_high > previous_high:

            score += 15

            reasons.append(
                "Higher High"
            )

        # ==========================
        # Higher Low
        # ==========================
        if recent_low > previous_low:

            score += 15

            reasons.append(
                "Higher Low"
            )

        # ==========================
        # Lower High
        # ==========================
        if recent_high < previous_high:

            score -= 15

            reasons.append(
                "Lower High"
            )

        # ==========================
        # Lower Low
        # ==========================
        if recent_low < previous_low:

            score -= 15

            reasons.append(
                "Lower Low"
            )

        # ==========================
        # Bullish BOS
        # ==========================
        if current_close > previous_high:

            score += 20

            reasons.append(
                "Bullish BOS"
            )

        # ==========================
        # Bearish Breakdown
        # ==========================
        if current_close < previous_low:

            score -= 20

            reasons.append(
                "Bearish Breakdown"
            )

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "recent_high": recent_high,
                "previous_high": previous_high,
                "recent_low": recent_low,
                "previous_low": previous_low
            }
        }

    except Exception as e:

        logger.error(
            f"Market structure failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Structure Error",
            "raw": {}
        }