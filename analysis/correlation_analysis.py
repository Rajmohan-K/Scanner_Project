from utils.logger import logger
import numpy as np


def calculate_corr(series1, series2):
    """
    Safely calculate Pearson correlation.
    """

    try:

        if len(series1) != len(series2):

            min_len = min(
                len(series1),
                len(series2)
            )

            series1 = series1[-min_len:]
            series2 = series2[-min_len:]

        return np.corrcoef(
            series1,
            series2
        )[0, 1]

    except:

        return 0


def run(
    stock_df,
    market_df,
    sector_df=None,
    **kwargs
):
    """
    Advanced Correlation Analysis
    """

    try:

        score = 0
        reasons = []

        stock_close = stock_df[
            "Close"
        ].tail(30).tolist()

        market_close = market_df[
            "Close"
        ].tail(30).tolist()

        market_corr = calculate_corr(
            stock_close,
            market_close
        )

        sector_corr = None

        # ==========================
        # Market Correlation Logic
        # ==========================
        if 0.3 <= market_corr <= 0.7:

            score += 15

            reasons.append(
                "Healthy Market Correlation"
            )

        elif market_corr > 0.85:

            score -= 5

            reasons.append(
                "Over Correlated To Market"
            )

        elif market_corr < 0.2:

            score += 10

            reasons.append(
                "Independent Strength"
            )

        # ==========================
        # Sector Correlation
        # ==========================
        if sector_df is not None:

            sector_close = sector_df[
                "Close"
            ].tail(30).tolist()

            sector_corr = calculate_corr(
                stock_close,
                sector_close
            )

            if 0.3 <= sector_corr <= 0.8:

                score += 10

                reasons.append(
                    "Healthy Sector Correlation"
                )

            elif sector_corr > 0.9:

                score -= 5

                reasons.append(
                    "Too Sector Dependent"
                )

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "market_corr": round(
                    market_corr, 2
                ),
                "sector_corr": round(
                    sector_corr, 2
                ) if sector_corr else None
            }
        }

    except Exception as e:

        logger.error(
            f"Correlation failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Correlation Error",
            "raw": {}
        }