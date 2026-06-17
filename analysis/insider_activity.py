from utils.logger import logger


def run(df, insider_data, **kwargs):
    """
    Advanced Insider Activity Analysis
    """

    try:

        score = 0
        reasons = []
        data_quality = str(insider_data.get("data_quality", "") or "").lower()
        if data_quality == "missing":
            return {
                "score": 0,
                "reason": "Insider data unavailable",
                "raw": insider_data,
            }

        buy_value = insider_data.get(
            "buy_value",
            0
        )

        sell_value = insider_data.get(
            "sell_value",
            0
        )

        net_transactions = insider_data.get(
            "net_transactions",
            0
        )

        promoter_change = insider_data.get(
            "promoter_change_percent",
            0
        )

        # ==========================
        # Net Buy/Sell
        # ==========================
        net_value = buy_value - sell_value

        if net_value > 0:

            score += 15

            reasons.append(
                "Net Insider Buying"
            )

        elif net_value < 0:

            score -= 15

            reasons.append(
                "Net Insider Selling"
            )

        # ==========================
        # Heavy Buying
        # ==========================
        if buy_value > sell_value * 2:

            score += 10

            reasons.append(
                "Strong Insider Accumulation"
            )

        # ==========================
        # Heavy Selling
        # ==========================
        if sell_value > buy_value * 2:

            score -= 10

            reasons.append(
                "Heavy Insider Distribution"
            )

        # ==========================
        # Transaction Count
        # ==========================
        if net_transactions >= 5:

            score += 5

            reasons.append(
                "Frequent Insider Activity"
            )

        # ==========================
        # Promoter Holding Change
        # ==========================
        if promoter_change > 0:

            score += 10

            reasons.append(
                "Promoter Stake Increased"
            )

        elif promoter_change < 0:

            score -= 10

            reasons.append(
                "Promoter Stake Reduced"
            )

        quality_multiplier = {
            "real": 1.0,
            "partial": 0.65,
            "proxy": 0.25,
        }.get(data_quality, 0.5)
        if quality_multiplier < 1:
            reasons.append(f"Data quality: {data_quality or 'unknown'}")

        return {
            "score": round(score * quality_multiplier, 2),
            "reason": ", ".join(reasons),
            "raw": {
                "net_value": net_value,
                "buy_value": buy_value,
                "sell_value": sell_value,
                "promoter_change": promoter_change,
                "source": insider_data.get("source", ""),
                "data_quality": insider_data.get("data_quality", ""),
            }
        }

    except Exception as e:

        logger.error(
            f"Insider analysis failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Insider Error",
            "raw": {}
        }
