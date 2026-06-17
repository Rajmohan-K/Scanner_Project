from utils.logger import logger


def detect_volatility_regime(df):
    """
    Classify volatility regime from recent realized volatility.
    """

    try:
        returns = df["Close"].pct_change().dropna()
        realized_vol = float(returns.tail(20).std() * 100)

        if realized_vol < 1.5:
            return {"regime": "Low Vol", "score": 10, "reason": "Low realized volatility", "volatility": round(realized_vol, 2)}
        if realized_vol < 3.0:
            return {"regime": "Normal Vol", "score": 4, "reason": "Manageable realized volatility", "volatility": round(realized_vol, 2)}
        if realized_vol < 4.5:
            return {"regime": "High Vol", "score": -6, "reason": "Elevated realized volatility", "volatility": round(realized_vol, 2)}
        return {"regime": "Extreme Vol", "score": -15, "reason": "Extreme realized volatility", "volatility": round(realized_vol, 2)}

    except Exception as exc:
        logger.error(f"Volatility regime failed: {exc}")
        return {"regime": "Unknown", "score": 0, "reason": "Volatility regime error", "volatility": 0}
