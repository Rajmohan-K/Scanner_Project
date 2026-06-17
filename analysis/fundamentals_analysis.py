from utils.logger import logger


def run(df, fundamentals_data, **kwargs):
    """
    Advanced Fundamentals Analysis
    """

    try:

        score = 0
        reasons = []
        data_quality = str(fundamentals_data.get("data_quality", "") or "").lower()
        if data_quality == "missing":
            return {
                "score": 0,
                "reason": "Fundamental data unavailable",
                "raw": fundamentals_data,
            }

        revenue_growth = fundamentals_data.get(
            "revenue_growth",
            0
        )

        profit_growth = fundamentals_data.get(
            "profit_growth",
            0
        )

        eps_growth = fundamentals_data.get(
            "eps_growth",
            0
        )

        roe = fundamentals_data.get(
            "roe",
            0
        )

        roce = fundamentals_data.get(
            "roce",
            0
        )

        debt_to_equity = fundamentals_data.get(
            "debt_to_equity",
            0
        )

        current_ratio = fundamentals_data.get(
            "current_ratio",
            0
        )

        pe_ratio = fundamentals_data.get(
            "pe_ratio",
            0
        )

        pb_ratio = fundamentals_data.get(
            "pb_ratio",
            0
        )

        promoter_holding = fundamentals_data.get(
            "promoter_holding",
            0
        )

        # ==========================
        # Revenue Growth
        # ==========================
        if revenue_growth >= 15:

            score += 10

            reasons.append(
                "Strong Revenue Growth"
            )

        elif revenue_growth >= 8:

            score += 5

            reasons.append(
                "Healthy Revenue Growth"
            )

        # ==========================
        # Profit Growth
        # ==========================
        if profit_growth >= 15:

            score += 10

            reasons.append(
                "Strong Profit Growth"
            )

        elif profit_growth >= 8:

            score += 5

            reasons.append(
                "Healthy Profit Growth"
            )

        # ==========================
        # EPS Growth
        # ==========================
        if eps_growth >= 15:

            score += 10

            reasons.append(
                "Strong EPS Growth"
            )

        # ==========================
        # ROE
        # ==========================
        if roe >= 15:

            score += 10

            reasons.append(
                "Healthy ROE"
            )

        # ==========================
        # ROCE
        # ==========================
        if roce >= 15:

            score += 10

            reasons.append(
                "Healthy ROCE"
            )

        # ==========================
        # Debt
        # ==========================
        if 0 < debt_to_equity <= 0.5:

            score += 10

            reasons.append(
                "Low Debt"
            )

        elif debt_to_equity > 2:

            score -= 10

            reasons.append(
                "High Debt"
            )

        # ==========================
        # Liquidity
        # ==========================
        if current_ratio >= 1.5:

            score += 5

            reasons.append(
                "Healthy Liquidity"
            )

        # ==========================
        # PE Valuation
        # ==========================
        if 0 < pe_ratio <= 25:

            score += 5

            reasons.append(
                "Reasonable PE"
            )

        elif pe_ratio > 60:

            score -= 5

            reasons.append(
                "Overvalued"
            )

        # ==========================
        # PB Ratio
        # ==========================
        if 0 < pb_ratio <= 5:

            score += 5

        # ==========================
        # Promoter Holding
        # ==========================
        if promoter_holding >= 50:

            score += 10

            reasons.append(
                "Strong Promoter Holding"
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
            "raw": fundamentals_data
        }

    except Exception as e:

        logger.error(
            f"Fundamentals failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Fundamental Error",
            "raw": {}
        }
