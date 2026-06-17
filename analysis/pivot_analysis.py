from utils.logger import logger


def run(df, **kwargs):
    """
    Advanced Pivot Analysis
    """

    try:

        score = 0
        reasons = []

        prev_high = df["High"].iloc[-2]
        prev_low = df["Low"].iloc[-2]
        prev_close = df["Close"].iloc[-2]

        current_price = df["Close"].iloc[-1]

        # ==========================
        # Pivot Calculation
        # ==========================
        pivot = (
            prev_high +
            prev_low +
            prev_close
        ) / 3

        r1 = (2 * pivot) - prev_low
        s1 = (2 * pivot) - prev_high

        r2 = pivot + (
            prev_high - prev_low
        )

        s2 = pivot - (
            prev_high - prev_low
        )

        # ==========================
        # Price Above Pivot
        # ==========================
        if current_price > pivot:

            score += 10

            reasons.append(
                "Above Pivot Bullish"
            )

        else:

            score -= 10

            reasons.append(
                "Below Pivot Bearish"
            )

        # ==========================
        # Near Resistance Breakout
        # ==========================
        if current_price > r1:

            score += 15

            reasons.append(
                "Above R1 Breakout"
            )

        if current_price > r2:

            score += 20

            reasons.append(
                "Above R2 Strong Breakout"
            )

        # ==========================
        # Near Support Breakdown
        # ==========================
        if current_price < s1:

            score -= 15

            reasons.append(
                "Below S1 Weakness"
            )

        if current_price < s2:

            score -= 20

            reasons.append(
                "Below S2 Breakdown"
            )

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "pivot": round(
                    pivot, 2
                ),
                "r1": round(
                    r1, 2
                ),
                "r2": round(
                    r2, 2
                ),
                "s1": round(
                    s1, 2
                ),
                "s2": round(
                    s2, 2
                )
            }
        }

    except Exception as e:

        logger.error(
            f"Pivot failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Pivot Error",
            "raw": {}
        }