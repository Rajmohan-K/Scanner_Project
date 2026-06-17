from utils.logger import logger


def run(df, **kwargs):
    """
    Advanced Smart Money Analysis
    """

    try:

        score = 0
        reasons = []

        close = df["Close"]
        open_ = df["Open"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]

        current_close = close.iloc[-1]
        current_open = open_.iloc[-1]
        current_high = high.iloc[-1]
        current_low = low.iloc[-1]
        current_volume = volume.iloc[-1]

        avg_volume = volume.tail(20).mean()

        # ==========================
        # Candle Metrics
        # ==========================
        body = abs(
            current_close -
            current_open
        )

        range_ = (
            current_high -
            current_low
        )

        body_ratio = (
            body / range_
            if range_ else 0
        )

        upper_wick = (
            current_high -
            max(
                current_close,
                current_open
            )
        )

        lower_wick = (
            min(
                current_close,
                current_open
            ) -
            current_low
        )

        volume_ratio = (
            current_volume /
            avg_volume
            if avg_volume else 0
        )

        # ==========================
        # Accumulation
        # ==========================
        if (
            current_close > current_open and
            volume_ratio > 1.5 and
            body_ratio > 0.6
        ):

            score += 20

            reasons.append(
                "Strong Accumulation"
            )

        # ==========================
        # Distribution
        # ==========================
        if (
            current_close < current_open and
            volume_ratio > 1.5 and
            body_ratio > 0.6
        ):

            score -= 20

            reasons.append(
                "Heavy Distribution"
            )

        # ==========================
        # Rejection Buying
        # ==========================
        if (
            lower_wick > body * 2 and
            current_close > current_open
        ):

            score += 10

            reasons.append(
                "Dip Bought"
            )

        # ==========================
        # Rejection Selling
        # ==========================
        if (
            upper_wick > body * 2 and
            current_close < current_open
        ):

            score -= 10

            reasons.append(
                "Selling Pressure"
            )

        # ==========================
        # Volume Confirmation
        # ==========================
        if volume_ratio > 2:

            score += 10

            reasons.append(
                "Institutional Volume"
            )

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "volume_ratio": round(
                    volume_ratio, 2
                ),
                "body_ratio": round(
                    body_ratio, 2
                )
            }
        }

    except Exception as e:

        logger.error(
            f"Smart money failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Smart Money Error",
            "raw": {}
        }