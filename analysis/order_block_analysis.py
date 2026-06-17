from utils.logger import logger


def run(df, **kwargs):
    """
    Advanced Order Block Analysis
    """

    try:

        score = 0
        reasons = []

        recent = df.tail(5)

        current_close = recent["Close"].iloc[-1]

        # Previous candle
        ob_open = recent["Open"].iloc[-2]
        ob_close = recent["Close"].iloc[-2]
        ob_high = recent["High"].iloc[-2]
        ob_low = recent["Low"].iloc[-2]

        # Current candle
        curr_open = recent["Open"].iloc[-1]
        curr_close = recent["Close"].iloc[-1]

        # ==========================
        # OB Candle Metrics
        # ==========================
        ob_body = abs(
            ob_close - ob_open
        )

        ob_range = ob_high - ob_low

        body_ratio = (
            ob_body / ob_range
            if ob_range else 0
        )

        # ==========================
        # Bullish Order Block
        # ==========================
        if (
            ob_close < ob_open and
            curr_close > curr_open and
            curr_close > ob_high and
            body_ratio > 0.5
        ):

            score += 20

            reasons.append(
                "Bullish Order Block"
            )

        # ==========================
        # Bearish Order Block
        # ==========================
        if (
            ob_close > ob_open and
            curr_close < curr_open and
            curr_close < ob_low and
            body_ratio > 0.5
        ):

            score -= 20

            reasons.append(
                "Bearish Order Block"
            )

        # ==========================
        # Retest Zone Detection
        # ==========================
        if (
            ob_low <= current_close <= ob_high
        ):

            score += 10

            reasons.append(
                "Inside OB Retest Zone"
            )

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "ob_high": round(
                    ob_high, 2
                ),
                "ob_low": round(
                    ob_low, 2
                ),
                "body_ratio": round(
                    body_ratio, 2
                )
            }
        }

    except Exception as e:

        logger.error(
            f"Order block failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Order Block Error",
            "raw": {}
        }