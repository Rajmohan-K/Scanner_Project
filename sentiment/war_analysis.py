from utils.logger import logger


def analyze_war_risk(
    war_data
):
    """
    Institutional Geopolitical Risk Engine
    """

    try:

        score = 0
        reasons = []

        conflict_level = war_data.get(
            "conflict_level",
            0
        )

        oil_risk = war_data.get(
            "oil_risk",
            0
        )

        regional_risk = war_data.get(
            "regional_risk",
            0
        )

        escalation = war_data.get(
            "escalation",
            False
        )

        # ==========================
        # Conflict Severity
        # ==========================
        if conflict_level >= 8:

            score -= 25
            reasons.append(
                "Extreme Conflict Risk"
            )

        elif conflict_level >= 5:

            score -= 15
            reasons.append(
                "Moderate Conflict Risk"
            )

        elif conflict_level >= 2:

            score -= 5
            reasons.append(
                "Minor Conflict Risk"
            )

        # ==========================
        # Oil/Commodity Risk
        # ==========================
        if oil_risk >= 8:

            score -= 20
            reasons.append(
                "Oil Shock Risk"
            )

        elif oil_risk >= 5:

            score -= 10
            reasons.append(
                "Commodity Risk Elevated"
            )

        # ==========================
        # Regional Risk
        # ==========================
        if regional_risk >= 7:

            score -= 15
            reasons.append(
                "Regional Instability"
            )

        elif regional_risk >= 4:

            score -= 8
            reasons.append(
                "Moderate Regional Risk"
            )

        # ==========================
        # Escalation Factor
        # ==========================
        if escalation:

            score -= 10
            reasons.append(
                "Conflict Escalating"
            )

        # ==========================
        # Final Label
        # ==========================
        if score <= -40:

            risk_level = "Extreme"

        elif score <= -25:

            risk_level = "High"

        elif score <= -10:

            risk_level = "Moderate"

        else:

            risk_level = "Low"

        return {
            "score":
                round(score, 2),

            "war_risk_level":
                risk_level,

            "headline_count":
                war_data.get(
                    "headline_count",
                    0
                ),

            "reason":
                ", ".join(reasons)
        }

    except Exception as e:

        logger.error(
            f"War analysis failed: {e}"
        )

        return {
            "score": 0,
            "war_risk_level": "Unknown"
        }
