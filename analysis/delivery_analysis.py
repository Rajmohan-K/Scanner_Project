from utils.logger import logger


def run(df, delivery_data, **kwargs):
    """
    Advanced Delivery Analysis
    """

    try:

        score = 0
        reasons = []
        data_quality = str(delivery_data.get("data_quality", "") or "").lower()
        if data_quality == "missing":
            return {
                "score": 0,
                "reason": "Delivery data unavailable",
                "raw": delivery_data,
            }

        current_close = df["Close"].iloc[-1]
        previous_close = df["Close"].iloc[-2]

        total_volume = df["Volume"].iloc[-1]

        current_delivery = delivery_data.get(
            "current_delivery_qty",
            0
        )

        avg_delivery = delivery_data.get(
            "avg_delivery_qty",
            0
        )

        # ==========================
        # Delivery %
        # ==========================
        delivery_percent = delivery_data.get("delivery_percent") or (
            (current_delivery / total_volume) * 100
            if total_volume else 0
        )

        # ==========================
        # Delivery Ratio
        # ==========================
        delivery_ratio = (
            current_delivery / avg_delivery
            if avg_delivery else 0
        )

        # ==========================
        # Strong Delivery Logic
        # ==========================
        if delivery_percent >= 60:

            score += 15

            reasons.append(
                "Very Strong Delivery"
            )

        elif delivery_percent >= 40:

            score += 10

            reasons.append(
                "Healthy Delivery"
            )

        # ==========================
        # Delivery Spike
        # ==========================
        if delivery_ratio >= 2:

            score += 15

            reasons.append(
                "Delivery Spike"
            )

        elif delivery_ratio >= 1.5:

            score += 10

            reasons.append(
                "Above Avg Delivery"
            )

        # ==========================
        # Accumulation
        # ==========================
        if (
            current_close > previous_close and
            delivery_percent > 50
        ):

            score += 10

            reasons.append(
                "Accumulation Detected"
            )

        # ==========================
        # Distribution
        # ==========================
        if (
            current_close < previous_close and
            delivery_percent > 50
        ):

            score -= 10

            reasons.append(
                "Distribution Detected"
            )

        quality_multiplier = {
            "real": 1.0,
            "partial": 0.65,
            "proxy": 0.30,
        }.get(data_quality, 0.5)
        if quality_multiplier < 1:
            reasons.append(f"Data quality: {data_quality or 'unknown'}")

        return {
            "score": round(score * quality_multiplier, 2),
            "reason": ", ".join(reasons),
            "raw": {
                "delivery_percent": round(
                    delivery_percent, 2
                ),
                "delivery_ratio": round(
                    delivery_ratio, 2
                ),
                "source": delivery_data.get("source", ""),
                "data_quality": delivery_data.get("data_quality", ""),
            }
        }

    except Exception as e:

        logger.error(
            f"Delivery failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Delivery Error",
            "raw": {}
        }
