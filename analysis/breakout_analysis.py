from utils.logger import logger
import numpy as np


def run(df, **kwargs):
    """
    Advanced Breakout Analysis
    Uses live OHLCV dataframe.
    """

    try:

        score = 0
        reasons = []

        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]
        open_price = df["Open"]

        latest_close = close.iloc[-1]
        latest_open = open_price.iloc[-1]
        latest_high = high.iloc[-1]
        latest_low = low.iloc[-1]
        latest_volume = volume.iloc[-1]

        # ==========================
        # Recent Resistance
        # ==========================
        resistance = high.tail(20).max()

        # Exclude latest candle from resistance
        resistance = high.iloc[-21:-1].max()

        breakout_percent = (
            (latest_close - resistance)
            / resistance
        ) * 100

        # ==========================
        # Volume Ratio
        # ==========================
        avg_volume = volume.tail(20).mean()

        volume_ratio = (
            latest_volume / avg_volume
            if avg_volume else 0
        )

        # ==========================
        # Candle Strength
        # ==========================
        candle_range = latest_high - latest_low

        candle_body = abs(
            latest_close - latest_open
        )

        candle_strength = (
            candle_body / candle_range
            if candle_range else 0
        )

        # ==========================
        # Breakout Logic
        # ==========================
        if latest_close > resistance:

            score += 15
            reasons.append(
                "Resistance Broken"
            )

        # ==========================
        # Strong Breakout %
        # ==========================
        if breakout_percent > 2:

            score += 10
            reasons.append(
                "Strong Breakout"
            )

        elif breakout_percent > 0.5:

            score += 5
            reasons.append(
                "Minor Breakout"
            )

        # ==========================
        # Volume Confirmation
        # ==========================
        if volume_ratio > 2:

            score += 15
            reasons.append(
                "Heavy Volume Breakout"
            )

        elif volume_ratio > 1.5:

            score += 10
            reasons.append(
                "Good Volume Confirmation"
            )

        # ==========================
        # Candle Strength
        # ==========================
        if candle_strength > 0.7:

            score += 10
            reasons.append(
                "Strong Bullish Candle"
            )

        elif candle_strength > 0.5:

            score += 5
            reasons.append(
                "Healthy Candle"
            )

        # ==========================
        # Fake Breakout Warning
        # ==========================
        upper_wick = latest_high - max(
            latest_close,
            latest_open
        )

        if upper_wick > candle_body:

            score -= 10
            reasons.append(
                "Possible Fake Breakout"
            )

        # ==========================
        # Overextended Warning
        # ==========================
        if breakout_percent > 5:

            score -= 5
            reasons.append(
                "Overextended Breakout"
            )

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "resistance": round(
                    resistance, 2
                ),
                "breakout_percent": round(
                    breakout_percent, 2
                ),
                "volume_ratio": round(
                    volume_ratio, 2
                ),
                "candle_strength": round(
                    candle_strength, 2
                )
            }
        }

    except Exception as e:

        logger.error(
            f"Breakout analysis failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Breakout Error",
            "raw": {}
        }