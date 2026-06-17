from utils.logger import logger


def detect_trend_regime(df):
    """
    Detect high-level trend regime from moving averages and slope.
    """

    try:
        close = df["Close"]
        ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
        ema200 = close.ewm(span=200, adjust=False).mean().iloc[-1]
        latest = close.iloc[-1]

        if latest > ema20 > ema50 > ema200:
            return {"regime": "Bull", "score": 20, "reason": "Aligned bullish trend"}
        if latest < ema20 < ema50 < ema200:
            return {"regime": "Bear", "score": -20, "reason": "Aligned bearish trend"}
        if latest > ema50:
            return {"regime": "Recovery", "score": 8, "reason": "Recovering above medium trend"}
        if latest < ema50:
            return {"regime": "Distribution", "score": -8, "reason": "Trading below medium trend"}
        return {"regime": "Sideways", "score": 0, "reason": "Mixed moving-average regime"}

    except Exception as exc:
        logger.error(f"Trend regime failed: {exc}")
        return {"regime": "Unknown", "score": 0, "reason": "Trend regime error"}
