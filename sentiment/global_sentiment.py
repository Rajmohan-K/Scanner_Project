from utils.logger import logger


def analyze_global_sentiment(
    global_data
):
    """
    Institutional Global Market Sentiment Engine
    """

    try:

        score = 0
        reasons = []

        sp500 = global_data.get(
            "sp500",
            0
        )

        nasdaq = global_data.get(
            "nasdaq",
            0
        )

        dow = global_data.get(
            "dow",
            0
        )

        nikkei = global_data.get(
            "nikkei",
            0
        )

        hang_seng = global_data.get(
            "hang_seng",
            0
        )

        vix = global_data.get(
            "vix",
            20
        )

        # ==========================
        # US Market Sentiment
        # ==========================
        us_avg = (
            sp500 +
            nasdaq +
            dow
        ) / 3

        if us_avg > 1:

            score += 20
            reasons.append(
                "Strong US Markets"
            )

        elif us_avg > 0:

            score += 10
            reasons.append(
                "Positive US Markets"
            )

        elif us_avg < -1:

            score -= 20
            reasons.append(
                "Weak US Markets"
            )

        elif us_avg < 0:

            score -= 10
            reasons.append(
                "Negative US Markets"
            )

        # ==========================
        # Asian Market Sentiment
        # ==========================
        asia_avg = (
            nikkei +
            hang_seng
        ) / 2

        if asia_avg > 1:

            score += 10
            reasons.append(
                "Asian Markets Bullish"
            )

        elif asia_avg < -1:

            score -= 10
            reasons.append(
                "Asian Markets Weak"
            )

        # ==========================
        # Fear Index
        # ==========================
        if vix > 30:

            score -= 20
            reasons.append(
                "Extreme Fear"
            )

        elif vix > 20:

            score -= 10
            reasons.append(
                "Elevated Fear"
            )

        elif vix < 15:

            score += 10
            reasons.append(
                "Low Fear Environment"
            )

        # ==========================
        # Final Sentiment Label
        # ==========================
        if score >= 25:

            sentiment = "Very Bullish"

        elif score >= 10:

            sentiment = "Bullish"

        elif score <= -25:

            sentiment = "Very Bearish"

        elif score <= -10:

            sentiment = "Bearish"

        else:

            sentiment = "Neutral"

        return {
            "score":
                round(score, 2),

            "sentiment":
                sentiment,

            "reason":
                ", ".join(reasons)
        }

    except Exception as e:

        logger.error(
            f"Global sentiment failed: {e}"
        )

        return {
            "score": 0,
            "sentiment": "Unknown"
        }