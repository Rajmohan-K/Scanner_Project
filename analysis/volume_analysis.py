from utils.logger import logger


def run(df, **kwargs):
    """
    Advanced Volume Analysis
    """

    try:

        score = 0
        reasons = []

        close = df["Close"]
        open_ = df["Open"]
        volume = df["Volume"]

        current_volume = volume.iloc[-1]

        avg_volume = volume.tail(20).mean()

        prev_avg_volume = volume.tail(50).mean()

        current_close = close.iloc[-1]

        prev_close = close.iloc[-2]

        current_open = open_.iloc[-1]

        # ==========================
        # Volume Ratio
        # ==========================
        volume_ratio = (
            current_volume / avg_volume
            if avg_volume else 0
        )

        # ==========================
        # Volume Spike
        # ==========================
        if volume_ratio >= 2:

            score += 20

            reasons.append(
                "Heavy Volume Spike"
            )

        elif volume_ratio >= 1.5:

            score += 10

            reasons.append(
                "Strong Volume"
            )

        elif volume_ratio < 0.7:

            score -= 10

            reasons.append(
                "Weak Volume"
            )

        # ==========================
        # Volume Trend
        # ==========================
        if avg_volume > prev_avg_volume:

            score += 10

            reasons.append(
                "Rising Volume Trend"
            )

        # ==========================
        # Bullish Price + Volume
        # ==========================
        if (
            current_close > prev_close and
            volume_ratio > 1.5
        ):

            score += 15

            reasons.append(
                "Bullish Volume Confirmation"
            )

        # ==========================
        # Bearish Price + Volume
        # ==========================
        if (
            current_close < prev_close and
            volume_ratio > 1.5
        ):

            score -= 15

            reasons.append(
                "Bearish Volume Selling"
            )

        # ==========================
        # Intraday Buying Interest
        # ==========================
        if (
            current_close > current_open and
            volume_ratio > 1.5
        ):

            score += 10

            reasons.append(
                "Intraday Buying Pressure"
            )

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "current_volume": round(
                    current_volume, 2
                ),
                "avg_volume": round(
                    avg_volume, 2
                ),
                "volume_ratio": round(
                    volume_ratio, 2
                )
            }
        }

    except Exception as e:

        logger.error(
            f"Volume failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Volume Error",
            "raw": {}
        }