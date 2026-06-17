from utils.logger import logger


def run(df, valuation_data, **kwargs):
    """
    Advanced Valuation Analysis
    """

    try:

        score = 0
        reasons = []
        data_quality = str(valuation_data.get("data_quality", "") or "").lower()
        if data_quality == "missing":
            return {
                "score": 0,
                "reason": "Valuation data unavailable",
                "raw": valuation_data,
            }

        pe_ratio = valuation_data.get(
            "pe_ratio",
            0
        )

        pb_ratio = valuation_data.get(
            "pb_ratio",
            0
        )

        peg_ratio = valuation_data.get(
            "peg_ratio",
            0
        )

        sector_pe = valuation_data.get(
            "sector_pe",
            0
        )

        sector_pb = valuation_data.get(
            "sector_pb",
            0
        )

        # ==========================
        # PE Analysis
        # ==========================
        if 0 < pe_ratio <= 15:

            score += 15

            reasons.append(
                "Low PE Attractive"
            )

        elif 0 < pe_ratio <= 25:

            score += 10

            reasons.append(
                "Healthy PE"
            )

        elif pe_ratio > 60:

            score -= 15

            reasons.append(
                "Highly Overvalued"
            )

        # ==========================
        # PB Analysis
        # ==========================
        if 0 < pb_ratio <= 3:

            score += 10

            reasons.append(
                "Low PB"
            )

        elif pb_ratio > 8:

            score -= 10

            reasons.append(
                "High PB"
            )

        # ==========================
        # PEG Analysis
        # ==========================
        if 0 < peg_ratio <= 1.5:

            score += 15

            reasons.append(
                "Healthy PEG"
            )

        elif peg_ratio > 3:

            score -= 10

            reasons.append(
                "Weak PEG"
            )

        # ==========================
        # Sector Comparison PE
        # ==========================
        if sector_pe:

            if pe_ratio < sector_pe:

                score += 10

                reasons.append(
                    "PE Below Sector Avg"
                )

            elif pe_ratio > sector_pe * 1.5:

                score -= 10

                reasons.append(
                    "PE Above Sector Avg"
                )

        # ==========================
        # Sector Comparison PB
        # ==========================
        if sector_pb:

            if pb_ratio < sector_pb:

                score += 5

                reasons.append(
                    "PB Below Sector Avg"
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
                "pe_ratio": pe_ratio,
                "pb_ratio": pb_ratio,
                "peg_ratio": peg_ratio,
                "source": valuation_data.get("source", ""),
                "data_quality": valuation_data.get("data_quality", ""),
            }
        }

    except Exception as e:

        logger.error(
            f"Valuation failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Valuation Error",
            "raw": {}
        }
