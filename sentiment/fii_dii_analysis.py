from utils.logger import logger


def analyze_fii_dii(
    flow_data
):
    """
    Institutional FII/DII Flow Analysis
    """

    try:

        score = 0
        reasons = []

        fii = flow_data.get(
            "fii",
            0
        )

        dii = flow_data.get(
            "dii",
            0
        )

        net_flow = fii + dii

        # ==========================
        # FII Analysis
        # ==========================
        if fii > 2000:

            score += 25
            reasons.append(
                "Strong FII Buying"
            )

        elif fii > 500:

            score += 10
            reasons.append(
                "Positive FII Flow"
            )

        elif fii < -2000:

            score -= 25
            reasons.append(
                "Heavy FII Selling"
            )

        elif fii < -500:

            score -= 10
            reasons.append(
                "Negative FII Flow"
            )

        # ==========================
        # DII Analysis
        # ==========================
        if dii > 1500:

            score += 15
            reasons.append(
                "Strong DII Buying"
            )

        elif dii < -1500:

            score -= 15
            reasons.append(
                "Strong DII Selling"
            )

        # ==========================
        # Combined Net Flow
        # ==========================
        if net_flow > 3000:

            score += 15
            reasons.append(
                "Massive Net Inflows"
            )

        elif net_flow < -3000:

            score -= 15
            reasons.append(
                "Massive Net Outflows"
            )

        # ==========================
        # Divergence Detection
        # ==========================
        if fii < 0 and dii > 0:

            reasons.append(
                "FII-DII Divergence"
            )

        # ==========================
        # Final Label
        # ==========================
        if score >= 30:

            sentiment = "Very Bullish"

        elif score >= 10:

            sentiment = "Bullish"

        elif score <= -30:

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

            "net_flow":
                net_flow,

            "source":
                flow_data.get(
                    "source",
                    "unknown"
                ),

            "confidence":
                flow_data.get(
                    "confidence",
                    0
                ),

            "reason":
                ", ".join(reasons)
        }

    except Exception as e:

        logger.error(
            f"FII/DII failed: {e}"
        )

        return {
            "score": 0,
            "sentiment": "Unknown"
        }
