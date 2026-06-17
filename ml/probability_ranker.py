from utils.logger import logger


def blend_probability(
    model_probability,
    score,
    confidence_pct,
    profitability_score,
):
    """
    Blend model probability with core scanner quality metrics.
    """

    try:
        blended = (
            (model_probability * 0.55) +
            (abs(score) * 1.20) +
            (confidence_pct * 0.20) +
            (max(profitability_score, 0) * 0.60)
        )
        return round(min(max(blended, 0), 100), 2)

    except Exception as exc:
        logger.error(f"Probability rank failed: {exc}")
        return 0.0
