from utils.logger import logger


def generate_signal(
    score,
    confidence,
    risk_level
):
    """
    Generate final trading signal
    """

    try:

        signal = "HOLD"

        # ==========================
        # Strong Buy
        # ==========================
        if (
            score >= 80 and
            confidence >= 75 and
            risk_level == "Low"
        ):

            signal = "STRONG BUY"

        # ==========================
        # Buy
        # ==========================
        elif (
            score >= 60 and
            confidence >= 60
        ):

            signal = "BUY"

        # ==========================
        # Weak Buy
        # ==========================
        elif (
            score >= 40 and
            confidence >= 50
        ):

            signal = "WEAK BUY"

        # ==========================
        # Strong Sell
        # ==========================
        elif (
            score <= -80 and
            confidence >= 75
        ):

            signal = "STRONG SELL"

        # ==========================
        # Sell
        # ==========================
        elif (
            score <= -60 and
            confidence >= 60
        ):

            signal = "SELL"

        return {
            "signal": signal
        }

    except Exception as e:

        logger.error(
            f"Signal engine failed: {e}"
        )

        return {
            "signal": "UNKNOWN"
        }
