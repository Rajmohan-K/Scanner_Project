from utils.logger import logger


def run(df, **kwargs):
    """
    Advanced Liquidity Analysis
    """

    try:

        score = 0
        reasons = []

        close = df["Close"]
        volume = df["Volume"]
        high = df["High"]
        low = df["Low"]

        latest_close = close.iloc[-1]

        latest_volume = volume.iloc[-1]

        avg_volume = volume.tail(20).mean()

        avg_turnover = (
            (close.tail(20) * volume.tail(20))
            .mean()
        )

        avg_range = (
            (high.tail(20) - low.tail(20))
            .mean()
        )

        liquidity_ratio = (
            latest_volume / avg_volume
            if avg_volume else 0
        )

        # ==========================
        # Avg Volume Check
        # ==========================
        if avg_volume >= 1000000:

            score += 15

            reasons.append(
                "High Average Volume"
            )

        elif avg_volume >= 500000:

            score += 10

            reasons.append(
                "Healthy Volume"
            )

        elif avg_volume < 100000:

            score -= 15

            reasons.append(
                "Low Liquidity"
            )

        # ==========================
        # Turnover Check
        # ==========================
        if avg_turnover >= 50000000:

            score += 15

            reasons.append(
                "Strong Turnover"
            )

        elif avg_turnover >= 10000000:

            score += 10

            reasons.append(
                "Healthy Turnover"
            )

        # ==========================
        # Liquidity Spike
        # ==========================
        if liquidity_ratio >= 2:

            score += 10

            reasons.append(
                "Liquidity Spike"
            )

        elif liquidity_ratio < 0.5:

            score -= 5

            reasons.append(
                "Low Participation"
            )

        # ==========================
        # Spread/Volatility Proxy
        # ==========================
        spread_proxy = (
            avg_range / latest_close
            if latest_close else 0
        )

        if spread_proxy < 0.03:

            score += 10

            reasons.append(
                "Stable Price Spread"
            )

        elif spread_proxy > 0.08:

            score -= 10

            reasons.append(
                "Wide Volatile Spread"
            )

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "avg_volume": round(
                    avg_volume, 2
                ),
                "avg_turnover": round(
                    avg_turnover, 2
                ),
                "liquidity_ratio": round(
                    liquidity_ratio, 2
                ),
                "spread_proxy": round(
                    spread_proxy, 4
                )
            }
        }

    except Exception as e:

        logger.error(
            f"Liquidity failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Liquidity Error",
            "raw": {}
        }