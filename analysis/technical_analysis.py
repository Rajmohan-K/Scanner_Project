from utils.logger import logger
import ta


def run(df, **kwargs):
    """
    Advanced Technical Analysis Engine
    """

    try:

        score = 0
        reasons = []

        close = df["Close"]

        # ==========================
        # RSI
        # ==========================
        rsi = ta.momentum.RSIIndicator(
            close
        ).rsi().iloc[-1]

        if 55 <= rsi <= 70:

            score += 10

            reasons.append(
                "Healthy RSI"
            )

        elif rsi > 70:

            score -= 5

            reasons.append(
                "Overbought"
            )

        elif rsi < 30:

            score += 10

            reasons.append(
                "Oversold Bounce Zone"
            )

        # ==========================
        # MACD
        # ==========================
        macd_obj = ta.trend.MACD(
            close
        )

        macd = macd_obj.macd().iloc[-1]

        macd_signal = (
            macd_obj
            .macd_signal()
            .iloc[-1]
        )

        if macd > macd_signal:

            score += 10

            reasons.append(
                "MACD Bullish"
            )

        else:

            score -= 10

            reasons.append(
                "MACD Bearish"
            )

        # ==========================
        # EMA Trend
        # ==========================
        ema20 = ta.trend.EMAIndicator(
            close,
            window=20
        ).ema_indicator().iloc[-1]

        ema50 = ta.trend.EMAIndicator(
            close,
            window=50
        ).ema_indicator().iloc[-1]

        current_price = close.iloc[-1]

        if (
            current_price >
            ema20 >
            ema50
        ):

            score += 15

            reasons.append(
                "Strong EMA Trend"
            )

        elif (
            current_price <
            ema20 <
            ema50
        ):

            score -= 15

            reasons.append(
                "Weak EMA Trend"
            )

        # ==========================
        # Bollinger Bands
        # ==========================
        bb = ta.volatility.BollingerBands(
            close
        )

        bb_high = (
            bb
            .bollinger_hband()
            .iloc[-1]
        )

        bb_low = (
            bb
            .bollinger_lband()
            .iloc[-1]
        )

        if current_price > bb_high:

            score -= 5

            reasons.append(
                "Above Upper BB"
            )

        elif current_price < bb_low:

            score += 5

            reasons.append(
                "Below Lower BB"
            )

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "rsi": round(
                    rsi, 2
                ),
                "macd": round(
                    macd, 2
                ),
                "ema20": round(
                    ema20, 2
                ),
                "ema50": round(
                    ema50, 2
                )
            }
        }

    except Exception as e:

        logger.error(
            f"Technical failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Technical Error",
            "raw": {}
        }