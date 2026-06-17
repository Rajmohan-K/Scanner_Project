from utils.logger import logger


def safe_ratio(a, b):
    """
    Safely calculate ratio.
    """
    try:
        return a / b if b else 0
    except:
        return 0


def percentage(part, total):
    """
    Safely calculate percentage.
    """
    try:
        return (part / total) * 100 if total else 0
    except:
        return 0


def run(market_data, **kwargs):
    """
    Advanced Breadth Analysis Engine
    """

    try:

        score = 0
        reasons = []

        advancers = market_data.get("advancers", 0)
        decliners = market_data.get("decliners", 0)

        new_highs = market_data.get("new_highs", 0)
        new_lows = market_data.get("new_lows", 0)

        above_ema20 = market_data.get("stocks_above_ema20", 0)
        above_ema50 = market_data.get("stocks_above_ema50", 0)
        above_ema200 = market_data.get("stocks_above_ema200", 0)

        total_stocks = market_data.get("total_stocks", 1)

        # ==========================
        # Advance Decline Ratio
        # ==========================
        adr = safe_ratio(
            advancers,
            decliners
        )

        if adr >= 2:
            score += 15
            reasons.append("Strong Advance Decline")

        elif adr >= 1.2:
            score += 10
            reasons.append("Positive Breadth")

        elif adr < 0.8:
            score -= 10
            reasons.append("Weak Breadth")

        # ==========================
        # New High / Low Ratio
        # ==========================
        hl_ratio = safe_ratio(
            new_highs,
            new_lows
        )

        if hl_ratio >= 2:
            score += 10
            reasons.append("Strong New Highs")

        elif hl_ratio < 1:
            score -= 5
            reasons.append("Weak New Highs")

        # ==========================
        # EMA Participation
        # ==========================
        ema20_pct = percentage(
            above_ema20,
            total_stocks
        )

        ema50_pct = percentage(
            above_ema50,
            total_stocks
        )

        ema200_pct = percentage(
            above_ema200,
            total_stocks
        )

        if ema20_pct > 60:
            score += 10
            reasons.append("Broad Short-Term Strength")

        if ema50_pct > 50:
            score += 10
            reasons.append("Broad Mid-Term Strength")

        if ema200_pct > 40:
            score += 10
            reasons.append("Long-Term Breadth Healthy")

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "adr": round(adr, 2),
                "hl_ratio": round(hl_ratio, 2),
                "ema20_pct": round(ema20_pct, 2),
                "ema50_pct": round(ema50_pct, 2),
                "ema200_pct": round(ema200_pct, 2)
            }
        }

    except Exception as e:

        logger.error(
            f"Breadth analysis failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Breadth Error",
            "raw": {}
        }