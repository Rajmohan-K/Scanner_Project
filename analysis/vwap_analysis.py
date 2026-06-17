from utils.logger import logger


def run(df, **kwargs):
    """
    Advanced VWAP Analysis
    """

    try:

        score = 0
        reasons = []

        high = df["High"]
        low = df["Low"]
        close = df["Close"]
        volume = df["Volume"]

        current_price = close.iloc[-1]

        # ==========================
        # Typical Price
        # ==========================
        typical_price = (
            high + low + close
        ) / 3

        # ==========================
        # VWAP Calculation
        # ==========================
        vwap = (
            (
                typical_price * volume
            ).cumsum() /
            volume.cumsum()
        ).iloc[-1]

        distance_pct = (
            abs(
                current_price - vwap
            ) / vwap
        ) * 100

        # ==========================
        # Above VWAP
        # ==========================
        if current_price > vwap:

            score += 15

            reasons.append(
                "Above VWAP Bullish"
            )

        else:

            score -= 15

            reasons.append(
                "Below VWAP Bearish"
            )

        # ==========================
        # Near VWAP
        # ==========================
        if distance_pct < 1:

            score += 5

            reasons.append(
                "Near Fair Value"
            )

        # ==========================
        # Extended Above VWAP
        # ==========================
        if current_price > vwap and distance_pct > 3:

            score -= 5

            reasons.append(
                "Overextended Above VWAP"
            )

        # ==========================
        # Extended Below VWAP
        # ==========================
        if current_price < vwap and distance_pct > 3:

            score += 5

            reasons.append(
                "Oversold Below VWAP"
            )

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "vwap": round(
                    vwap, 2
                ),
                "distance_pct": round(
                    distance_pct, 2
                )
            }
        }

    except Exception as e:

        logger.error(
            f"VWAP failed: {e}"
        )

        return {
            "score": 0,
            "reason": "VWAP Error",
            "raw": {}
        }