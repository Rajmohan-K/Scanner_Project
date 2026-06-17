from utils.logger import logger


def calculate_fib_levels(high, low):
    """
    Calculate Fibonacci retracement levels.
    """

    diff = high - low

    return {
        "0": high,
        "23.6": high - diff * 0.236,
        "38.2": high - diff * 0.382,
        "50": high - diff * 0.500,
        "61.8": high - diff * 0.618,
        "78.6": high - diff * 0.786,
        "100": low
    }


def run(df, **kwargs):
    """
    Advanced Fibonacci Analysis
    """

    try:

        score = 0
        reasons = []

        current_price = df["Close"].iloc[-1]

        # ==========================
        # Auto Swing Detection
        # ==========================
        swing_high = df[
            "High"
        ].tail(20).max()

        swing_low = df[
            "Low"
        ].tail(20).min()

        fib_levels = calculate_fib_levels(
            swing_high,
            swing_low
        )

        # ==========================
        # Find Nearest Fib Level
        # ==========================
        nearest_level = min(
            fib_levels.items(),
            key=lambda x: abs(
                x[1] - current_price
            )
        )

        fib_name = nearest_level[0]
        fib_price = nearest_level[1]

        # ==========================
        # Golden Zone
        # ==========================
        if fib_name in ["50", "61.8"]:

            score += 15

            reasons.append(
                "Golden Zone Support"
            )

        # ==========================
        # Healthy Pullback
        # ==========================
        elif fib_name == "38.2":

            score += 10

            reasons.append(
                "Healthy Pullback Zone"
            )

        # ==========================
        # Deep Retracement
        # ==========================
        elif fib_name == "78.6":

            score += 5

            reasons.append(
                "Deep Retracement"
            )

        # ==========================
        # Breakout High
        # ==========================
        elif fib_name == "0":

            score += 10

            reasons.append(
                "Near Swing High"
            )

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "swing_high": round(
                    swing_high, 2
                ),
                "swing_low": round(
                    swing_low, 2
                ),
                "nearest_fib": fib_name,
                "nearest_price": round(
                    fib_price, 2
                ),
                "fib_levels": {
                    k: round(v, 2)
                    for k, v in fib_levels.items()
                }
            }
        }

    except Exception as e:

        logger.error(
            f"Fibonacci failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Fib Error",
            "raw": {}
        }