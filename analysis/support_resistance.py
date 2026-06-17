from utils.logger import logger


def run(df, **kwargs):
    """
    Advanced Support Resistance Analysis
    """

    try:

        score = 0
        reasons = []

        highs = df["High"]
        lows = df["Low"]
        close = df["Close"]

        current_price = close.iloc[-1]

        # ==========================
        # Dynamic Zones
        # ==========================
        resistance_window = highs.iloc[-21:-1] if len(highs) > 20 else highs.iloc[:-1]
        support_window = lows.iloc[-21:-1] if len(lows) > 20 else lows.iloc[:-1]

        resistance = resistance_window.max()

        support = support_window.min()

        # ==========================
        # Distance %
        # ==========================
        resistance_distance = (
            abs(
                resistance - current_price
            ) / current_price
        ) * 100

        support_distance = (
            abs(
                current_price - support
            ) / current_price
        ) * 100

        # ==========================
        # Near Support
        # ==========================
        if support_distance < 2:

            score += 15

            reasons.append(
                "Near Support"
            )

        # ==========================
        # Near Resistance
        # ==========================
        if resistance_distance < 2:

            score -= 10

            reasons.append(
                "Near Resistance"
            )

        # ==========================
        # Resistance Breakout
        # ==========================
        if current_price > resistance:

            score += 20

            reasons.append(
                "Resistance Breakout"
            )

        # ==========================
        # Support Breakdown
        # ==========================
        if current_price < support:

            score -= 20

            reasons.append(
                "Support Breakdown"
            )

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "support": round(
                    support, 2
                ),
                "resistance": round(
                    resistance, 2
                ),
                "support_distance": round(
                    support_distance, 2
                ),
                "resistance_distance": round(
                    resistance_distance, 2
                )
            }
        }

    except Exception as e:

        logger.error(
            f"Support resistance failed: {e}"
        )

        return {
            "score": 0,
            "reason": "SR Error",
            "raw": {}
        }
