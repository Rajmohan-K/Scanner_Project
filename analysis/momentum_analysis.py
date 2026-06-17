from utils.logger import logger


def run(df, **kwargs):
    """
    Advanced Momentum Analysis
    """

    try:

        score = 0
        reasons = []

        close = df["Close"]

        latest_close = close.iloc[-1]

        prev_close = close.iloc[-2]

        close_5 = close.iloc[-6]

        close_10 = close.iloc[-11]

        # ==========================
        # 5 Period Momentum
        # ==========================
        momentum_5 = (
            (
                latest_close - close_5
            ) / close_5
        ) * 100

        # ==========================
        # 10 Period Momentum
        # ==========================
        momentum_10 = (
            (
                latest_close - close_10
            ) / close_10
        ) * 100

        # ==========================
        # Daily Momentum
        # ==========================
        daily_momentum = (
            (
                latest_close - prev_close
            ) / prev_close
        ) * 100

        # ==========================
        # Positive Momentum
        # ==========================
        if momentum_5 > 3:

            score += 10

            reasons.append(
                "Strong Short Momentum"
            )

        elif momentum_5 > 1:

            score += 5

            reasons.append(
                "Positive Momentum"
            )

        # ==========================
        # Medium Momentum
        # ==========================
        if momentum_10 > 5:

            score += 15

            reasons.append(
                "Strong Mid Momentum"
            )

        elif momentum_10 < -5:

            score -= 15

            reasons.append(
                "Weak Mid Momentum"
            )

        # ==========================
        # Acceleration
        # ==========================
        if momentum_5 > momentum_10:

            score += 10

            reasons.append(
                "Momentum Accelerating"
            )

        # ==========================
        # Daily Spike
        # ==========================
        if daily_momentum > 2:

            score += 10

            reasons.append(
                "Daily Momentum Spike"
            )

        elif daily_momentum < -2:

            score -= 10

            reasons.append(
                "Daily Weakness"
            )

        # ==========================
        # Consecutive Green Candles
        # ==========================
        recent_closes = close.tail(4).tolist()

        green_count = 0

        for i in range(1, len(recent_closes)):

            if recent_closes[i] > recent_closes[i - 1]:

                green_count += 1

        if green_count >= 3:

            score += 10

            reasons.append(
                "Strong Consecutive Buying"
            )

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "momentum_5": round(
                    momentum_5, 2
                ),
                "momentum_10": round(
                    momentum_10, 2
                ),
                "daily_momentum": round(
                    daily_momentum, 2
                )
            }
        }

    except Exception as e:

        logger.error(
            f"Momentum failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Momentum Error",
            "raw": {}
        }