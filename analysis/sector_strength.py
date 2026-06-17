from utils.logger import logger


def calculate_return(series):
    """
    Calculate % return
    """

    try:

        start = series.iloc[0]
        end = series.iloc[-1]

        return (
            (
                end - start
            ) / start
        ) * 100

    except:

        return 0


def run(
    stock_df,
    sector_df,
    **kwargs
):
    """
    Advanced Sector Strength Analysis
    """

    try:

        score = 0
        reasons = []

        stock_return = calculate_return(
            stock_df["Close"].tail(20)
        )

        sector_return = calculate_return(
            sector_df["Close"].tail(20)
        )

        performance_diff = (
            stock_return -
            sector_return
        )

        # ==========================
        # Sector Overall Strength
        # ==========================
        if sector_return > 5:

            score += 15

            reasons.append(
                "Strong Sector"
            )

        elif sector_return > 2:

            score += 10

            reasons.append(
                "Positive Sector"
            )

        elif sector_return < -5:

            score -= 15

            reasons.append(
                "Weak Sector"
            )

        elif sector_return < -2:

            score -= 10

            reasons.append(
                "Negative Sector"
            )

        # ==========================
        # Stock vs Sector
        # ==========================
        if performance_diff > 3:

            score += 15

            reasons.append(
                "Sector Leader"
            )

        elif performance_diff < -3:

            score -= 15

            reasons.append(
                "Sector Laggard"
            )

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "stock_return": round(
                    stock_return, 2
                ),
                "sector_return": round(
                    sector_return, 2
                ),
                "performance_diff": round(
                    performance_diff, 2
                )
            }
        }

    except Exception as e:

        logger.error(
            f"Sector strength failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Sector Error",
            "raw": {}
        }