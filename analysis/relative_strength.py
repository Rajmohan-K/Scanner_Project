from utils.logger import logger


def calculate_return(series):
    """
    Calculate percentage return.
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
    benchmark_df,
    sector_df=None,
    **kwargs
):
    """
    Advanced Relative Strength Analysis
    """

    try:

        score = 0
        reasons = []

        stock_return = calculate_return(
            stock_df["Close"].tail(20)
        )

        benchmark_return = calculate_return(
            benchmark_df["Close"].tail(20)
        )

        rs_value = (
            stock_return -
            benchmark_return
        )

        # ==========================
        # Benchmark Comparison
        # ==========================
        if rs_value > 5:

            score += 20

            reasons.append(
                "Strong Outperformance"
            )

        elif rs_value > 2:

            score += 10

            reasons.append(
                "Positive Relative Strength"
            )

        elif rs_value < -5:

            score -= 20

            reasons.append(
                "Major Underperformance"
            )

        elif rs_value < -2:

            score -= 10

            reasons.append(
                "Weak Relative Strength"
            )

        sector_rs = None

        # ==========================
        # Sector Comparison
        # ==========================
        if sector_df is not None:

            sector_return = calculate_return(
                sector_df["Close"].tail(20)
            )

            sector_rs = (
                stock_return -
                sector_return
            )

            if sector_rs > 3:

                score += 10

                reasons.append(
                    "Sector Outperformer"
                )

            elif sector_rs < -3:

                score -= 10

                reasons.append(
                    "Sector Underperformer"
                )

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "stock_return": round(
                    stock_return, 2
                ),
                "benchmark_return": round(
                    benchmark_return, 2
                ),
                "relative_strength": round(
                    rs_value, 2
                ),
                "sector_rs": round(
                    sector_rs, 2
                ) if sector_rs else None
            }
        }

    except Exception as e:

        logger.error(
            f"Relative strength failed: {e}"
        )

        return {
            "score": 0,
            "reason": "RS Error",
            "raw": {}
        }