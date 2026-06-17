from utils.logger import logger


def generate_signal(
    score,
    confidence_pct,
    risk_level
):
    """
    Generate final trading signal
    """

    try:

        signal = "HOLD"
        strength = 0
        reasons = []

        # ==========================
        # Strong Buy
        # ==========================
        if (
            score >= 80 and
            confidence_pct >= 75 and
            risk_level == "Low"
        ):

            signal = "STRONG BUY"
            strength = 100

            reasons.append(
                "Elite bullish setup"
            )

        # ==========================
        # Buy
        # ==========================
        elif (
            score >= 60 and
            confidence_pct >= 60
        ):

            signal = "BUY"
            strength = 80

            reasons.append(
                "Bullish setup"
            )

        # ==========================
        # Weak Buy
        # ==========================
        elif (
            score >= 40 and
            confidence_pct >= 50
        ):

            signal = "WEAK BUY"
            strength = 60

            reasons.append(
                "Moderate bullish bias"
            )

        # ==========================
        # Strong Sell
        # ==========================
        elif (
            score <= -80 and
            confidence_pct >= 75
        ):

            signal = "STRONG SELL"
            strength = 100

            reasons.append(
                "Elite bearish setup"
            )

        # ==========================
        # Sell
        # ==========================
        elif (
            score <= -60 and
            confidence_pct >= 60
        ):

            signal = "SELL"
            strength = 80

            reasons.append(
                "Bearish setup"
            )

        # ==========================
        # Weak Sell
        # ==========================
        elif (
            score <= -40 and
            confidence_pct >= 50
        ):

            signal = "WEAK SELL"
            strength = 60

            reasons.append(
                "Moderate bearish bias"
            )

        else:

            signal = "HOLD"
            strength = 30

            reasons.append(
                "No clear setup"
            )

        return {
            "signal": signal,
            "signal_strength": strength,
            "reason": ", ".join(
                reasons
            )
        }

    except Exception as e:

        logger.error(
            f"Signal engine failed: {e}"
        )

        return {
            "signal": "UNKNOWN",
            "signal_strength": 0
        }