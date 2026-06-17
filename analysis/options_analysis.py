from utils.logger import logger


def run(df, options_data, **kwargs):
    """
    Advanced Options Analysis
    """

    try:

        score = 0
        reasons = []
        data_quality = str(options_data.get("data_quality", "") or "").lower()
        if data_quality == "missing":
            return {
                "score": 0,
                "reason": "Options data unavailable",
                "raw": options_data,
            }

        current_price = df["Close"].iloc[-1]

        pcr = options_data.get(
            "pcr",
            0
        )

        max_pain = options_data.get(
            "max_pain",
            0
        )

        call_oi = options_data.get(
            "call_oi",
            0
        )

        put_oi = options_data.get(
            "put_oi",
            0
        )

        call_oi_change = options_data.get(
            "call_oi_change",
            0
        )

        put_oi_change = options_data.get(
            "put_oi_change",
            0
        )

        iv = options_data.get(
            "iv",
            0
        )

        # ==========================
        # PCR Logic
        # ==========================
        if pcr >= 1.2:

            score += 15

            reasons.append(
                "Bullish PCR"
            )

        elif pcr < 0.8:

            score -= 15

            reasons.append(
                "Bearish PCR"
            )

        # ==========================
        # OI Strength
        # ==========================
        if put_oi > call_oi:

            score += 10

            reasons.append(
                "Put Support Strong"
            )

        elif call_oi > put_oi:

            score -= 10

            reasons.append(
                "Call Resistance Strong"
            )

        # ==========================
        # OI Change Logic
        # ==========================
        if (
            put_oi_change > 0 and
            call_oi_change < 0
        ):

            score += 15

            reasons.append(
                "Bullish OI Build"
            )

        elif (
            call_oi_change > 0 and
            put_oi_change < 0
        ):

            score -= 15

            reasons.append(
                "Bearish OI Build"
            )

        # ==========================
        # Max Pain Proximity
        # ==========================
        pain_distance = (
            abs(current_price - max_pain) / current_price * 100
            if current_price and max_pain
            else 0
        )

        if max_pain and pain_distance < 2:

            score += 5

            reasons.append(
                "Near Max Pain"
            )

        # ==========================
        # IV Analysis
        # ==========================
        if iv > 30:

            score -= 5

            reasons.append(
                "High Volatility Risk"
            )

        elif 0 < iv < 15:

            score += 5

            reasons.append(
                "Low IV Stable"
            )

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "pcr": pcr,
                "max_pain": max_pain,
                "iv": iv,
                "source": options_data.get("source", ""),
                "data_quality": options_data.get("data_quality", ""),
                "pain_distance": round(
                    pain_distance, 2
                )
            }
        }

    except Exception as e:

        logger.error(
            f"Options failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Options Error",
            "raw": {}
        }
