from utils.logger import logger
import numpy as np


def run(df, **kwargs):
    """
    Advanced Trend Analysis
    """

    try:

        score = 0
        reasons = []

        closes = df["Close"].tail(20)

        highs = df["High"].tail(20)

        lows = df["Low"].tail(20)

        # ==========================
        # Linear Trend Slope
        # ==========================
        x = np.arange(len(closes))

        slope = np.polyfit(
            x,
            closes,
            1
        )[0]

        # ==========================
        # Higher High / Higher Low
        # ==========================
        recent_high = highs.tail(5).max()

        old_high = highs.head(5).max()

        recent_low = lows.tail(5).min()

        old_low = lows.head(5).min()

        # ==========================
        # Consecutive Trend Closes
        # ==========================
        up_closes = sum(
            closes.iloc[i] >
            closes.iloc[i - 1]
            for i in range(1, len(closes))
        )

        down_closes = sum(
            closes.iloc[i] <
            closes.iloc[i - 1]
            for i in range(1, len(closes))
        )

        # ==========================
        # Slope Trend
        # ==========================
        if slope > 1:

            score += 15

            reasons.append(
                "Strong Uptrend Slope"
            )

        elif slope > 0:

            score += 10

            reasons.append(
                "Positive Trend"
            )

        elif slope < -1:

            score -= 15

            reasons.append(
                "Strong Downtrend"
            )

        elif slope < 0:

            score -= 10

            reasons.append(
                "Negative Trend"
            )

        # ==========================
        # Higher High/Low
        # ==========================
        if recent_high > old_high:

            score += 10

            reasons.append(
                "Higher High"
            )

        if recent_low > old_low:

            score += 10

            reasons.append(
                "Higher Low"
            )

        if recent_high < old_high:

            score -= 10

            reasons.append(
                "Lower High"
            )

        if recent_low < old_low:

            score -= 10

            reasons.append(
                "Lower Low"
            )

        # ==========================
        # Trend Consistency
        # ==========================
        if up_closes > 12:

            score += 10

            reasons.append(
                "Consistent Buying"
            )

        elif down_closes > 12:

            score -= 10

            reasons.append(
                "Consistent Selling"
            )

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "slope": round(
                    slope, 2
                ),
                "up_closes": up_closes,
                "down_closes": down_closes
            }
        }

    except Exception as e:

        logger.error(
            f"Trend failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Trend Error",
            "raw": {}
        }