from utils.logger import logger


def calculate_confidence(module_results):
    """
    Calculate scanner confidence percentage
    based on bullish/bearish agreement.
    """

    try:

        if not module_results:

            return {
                "confidence_pct": 0
            }

        total_modules = len(module_results)

        bullish_count = 0
        bearish_count = 0

        for module, result in module_results.items():

            score = result.get(
                "score",
                0
            )

            if score > 0:

                bullish_count += 1

            elif score < 0:

                bearish_count += 1

        dominant = max(
            bullish_count,
            bearish_count
        )

        confidence_pct = (
            dominant / total_modules
        ) * 100

        return {
            "confidence_pct": round(
                confidence_pct,
                2
            ),

            "bullish_modules":
                bullish_count,

            "bearish_modules":
                bearish_count
        }

    except Exception as e:

        logger.error(
            f"Confidence failed: {e}"
        )

        return {
            "confidence_pct": 0
        }