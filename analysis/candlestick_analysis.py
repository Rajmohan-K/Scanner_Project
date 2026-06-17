from utils.logger import logger


def run(df, **kwargs):
    """
    Advanced Candlestick Analysis
    Uses live OHLC dataframe.
    """

    try:

        score = 0
        reasons = []

        # ==========================
        # Current Candle
        # ==========================
        open_price = df["Open"].iloc[-1]
        high = df["High"].iloc[-1]
        low = df["Low"].iloc[-1]
        close = df["Close"].iloc[-1]

        # ==========================
        # Previous Candle
        # ==========================
        prev_open = df["Open"].iloc[-2]
        prev_close = df["Close"].iloc[-2]

        # ==========================
        # Candle Metrics
        # ==========================
        body = abs(close - open_price)

        total_range = high - low

        upper_wick = high - max(
            close,
            open_price
        )

        lower_wick = min(
            close,
            open_price
        ) - low

        body_ratio = (
            body / total_range
            if total_range else 0
        )

        # ==========================
        # Doji Detection
        # ==========================
        if body_ratio < 0.1:

            score += 2
            reasons.append("Doji")

        # ==========================
        # Hammer Detection
        # ==========================
        if (
            lower_wick > body * 2 and
            upper_wick < body
        ):

            score += 15
            reasons.append("Hammer")

        # ==========================
        # Shooting Star
        # ==========================
        if (
            upper_wick > body * 2 and
            lower_wick < body
        ):

            score -= 15
            reasons.append(
                "Shooting Star"
            )

        # ==========================
        # Bullish Engulfing
        # ==========================
        if (
            prev_close < prev_open and
            close > open_price and
            open_price < prev_close and
            close > prev_open
        ):

            score += 20
            reasons.append(
                "Bullish Engulfing"
            )

        # ==========================
        # Bearish Engulfing
        # ==========================
        if (
            prev_close > prev_open and
            close < open_price and
            open_price > prev_close and
            close < prev_open
        ):

            score -= 20
            reasons.append(
                "Bearish Engulfing"
            )

        # ==========================
        # Strong Bull Candle
        # ==========================
        if (
            close > open_price and
            body_ratio > 0.7
        ):

            score += 10
            reasons.append(
                "Strong Bull Candle"
            )

        # ==========================
        # Strong Bear Candle
        # ==========================
        if (
            close < open_price and
            body_ratio > 0.7
        ):

            score -= 10
            reasons.append(
                "Strong Bear Candle"
            )

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "body_ratio": round(
                    body_ratio, 2
                ),
                "upper_wick": round(
                    upper_wick, 2
                ),
                "lower_wick": round(
                    lower_wick, 2
                )
            }
        }

    except Exception as e:

        logger.error(
            f"Candlestick analysis failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Candlestick Error",
            "raw": {}
        }