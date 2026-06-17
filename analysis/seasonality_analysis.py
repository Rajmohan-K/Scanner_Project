from utils.logger import logger
import pandas as pd


def run(df, **kwargs):
    """
    Advanced Seasonality Analysis
    """

    try:

        score = 0
        reasons = []

        data = df.copy()

        # ==========================
        # Ensure Datetime Index
        # ==========================
        data.index = pd.to_datetime(
            data.index
        )

        # ==========================
        # Monthly Returns
        # ==========================
        data["Month"] = data.index.month

        data["Return"] = (
            data["Close"]
            .pct_change()
        )

        monthly_returns = (
            data.groupby("Month")[
                "Return"
            ].mean()
        )

        current_month = pd.Timestamp.now().month

        month_avg_return = monthly_returns.get(
            current_month,
            0
        ) * 100

        # ==========================
        # Day of Week Returns
        # ==========================
        data["Weekday"] = (
            data.index.dayofweek
        )

        weekday_returns = (
            data.groupby("Weekday")[
                "Return"
            ].mean()
        )

        current_day = pd.Timestamp.now(
        ).dayofweek

        day_avg_return = weekday_returns.get(
            current_day,
            0
        ) * 100

        # ==========================
        # Monthly Bias
        # ==========================
        if month_avg_return > 1:

            score += 15

            reasons.append(
                "Bullish Monthly Seasonality"
            )

        elif month_avg_return < -1:

            score -= 15

            reasons.append(
                "Bearish Monthly Seasonality"
            )

        # ==========================
        # Weekly Bias
        # ==========================
        if day_avg_return > 0.3:

            score += 10

            reasons.append(
                "Bullish Day Bias"
            )

        elif day_avg_return < -0.3:

            score -= 10

            reasons.append(
                "Bearish Day Bias"
            )

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "month_avg_return": round(
                    month_avg_return, 2
                ),
                "day_avg_return": round(
                    day_avg_return, 2
                )
            }
        }

    except Exception as e:

        logger.error(
            f"Seasonality failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Seasonality Error",
            "raw": {}
        }