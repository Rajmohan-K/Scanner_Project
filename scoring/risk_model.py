from utils.logger import logger


def calculate_risk(risk_inputs):
    """
    Calculate risk level based on
    volatility + confidence, and
    provide position sizing guidance.
    """

    try:
        volatility = risk_inputs.get("volatility", 0)
        confidence_pct = risk_inputs.get("confidence_pct", 0)
        account_capital = float(risk_inputs.get("account_capital", 100000) or 100000)
        entry = float(risk_inputs.get("entry", 0) or 0)
        stoploss = float(risk_inputs.get("stoploss", 0) or 0)
        target = float(risk_inputs.get("target", 0) or 0)

        risk_score = 0
        reasons = []

        if volatility > 4:
            risk_score += 40
            reasons.append("Very High Volatility")
        elif volatility > 2:
            risk_score += 25
            reasons.append("Moderate Volatility")
        else:
            risk_score += 10
            reasons.append("Low Volatility")

        if confidence_pct >= 80:
            risk_score -= 20
            reasons.append("High Confidence")
        elif confidence_pct >= 60:
            risk_score -= 10
            reasons.append("Good Confidence")
        elif confidence_pct < 40:
            risk_score += 8
            reasons.append("Low Confidence")

        if risk_score >= 40:
            risk_level = "High"
        elif risk_score >= 20:
            risk_level = "Medium"
        else:
            risk_level = "Low"

        recommended_risk_pct = {
            "Low": 1.0,
            "Medium": 0.75,
            "High": 0.5,
        }.get(risk_level, 0.5)

        stop_distance = abs(entry - stoploss) if entry and stoploss else 0
        position_size = 0.0
        expected_return = 0.0
        if stop_distance > 0:
            position_size = round((account_capital * (recommended_risk_pct / 100)) / stop_distance, 2)
            reward_distance = abs(target - entry) if target and entry else stop_distance
            expected_return = round(position_size * reward_distance, 2)

        return {
            "risk_score": round(risk_score, 2),
            "risk_level": risk_level,
            "recommended_risk_pct": recommended_risk_pct,
            "position_size": position_size,
            "expected_return": expected_return,
            "reason": ", ".join(reasons),
        }

    except Exception as e:

        logger.error(
            f"Risk model failed: {e}"
        )

        return {
            "risk_score": 0,
            "risk_level": "Unknown"
        }
