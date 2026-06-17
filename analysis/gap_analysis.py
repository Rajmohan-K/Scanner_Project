from utils.logger import logger


def run(df, **kwargs):
    """
    Advanced Gap Analysis
    Uses OHLCV dataframe.
    """

    try:

        score = 0
        reasons = []

        # ==========================
        # Required Prices
        # ==========================
        today_open = df["Open"].iloc[-1]

        previous_close = df["Close"].iloc[-2]

        current_volume = df["Volume"].iloc[-1]

        avg_volume = df["Volume"].tail(20).mean()

        # ==========================
        # Gap Calculation
        # ==========================
        gap_percent = (
            (
                today_open - previous_close
            )
            / previous_close
        ) * 100

        # ==========================
        # Volume Ratio
        # ==========================
        volume_ratio = (
            current_volume / avg_volume
            if avg_volume else 0
        )

        # ==========================
        # Bullish Gap Logic
        # ==========================
        if gap_percent > 0.5:

            if gap_percent >= 2:

                score += 15

                reasons.append(
                    "Strong Gap Up"
                )

            else:

                score += 10

                reasons.append(
                    "Moderate Gap Up"
                )

        # ==========================
        # Bearish Gap Logic
        # ==========================
        elif gap_percent < -0.5:

            if gap_percent <= -2:

                score -= 15

                reasons.append(
                    "Strong Gap Down"
                )

            else:

                score -= 10

                reasons.append(
                    "Moderate Gap Down"
                )

        # ==========================
        # Volume Confirmation
        # ==========================
        if volume_ratio >= 2:

            score += 10

            reasons.append(
                "Gap Volume Confirmed"
            )

        elif volume_ratio < 0.8:

            score -= 5

            reasons.append(
                "Weak Gap Volume"
            )

        # ==========================
        # Exhaustion Gap Warning
        # ==========================
        if abs(gap_percent) > 5:

            score -= 10

            reasons.append(
                "Possible Exhaustion Gap"
            )

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "gap_percent": round(
                    gap_percent, 2
                ),
                "volume_ratio": round(
                    volume_ratio, 2
                )
            }
        }

    except Exception as e:

        logger.error(
            f"Gap analysis failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Gap Error",
            "raw": {}
        }