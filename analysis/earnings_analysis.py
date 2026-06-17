from utils.logger import logger
from datetime import datetime


def calculate_growth(current, previous):
    """
    Safe growth calculator.
    """
    try:

        if previous == 0:
            return 0

        return (
            (current - previous)
            / previous
        ) * 100

    except:

        return 0


def get_days_to_earnings(earnings_date):
    """
    Days remaining until earnings.
    """
    try:

        today = datetime.today()

        earnings_dt = datetime.strptime(
            earnings_date,
            "%Y-%m-%d"
        )

        return (
            earnings_dt - today
        ).days

    except:

        return None


def run(df, earnings_data, **kwargs):
    """
    Advanced Earnings Analysis
    """

    try:

        score = 0
        reasons = []

        earnings_date = earnings_data.get(
            "earnings_date"
        )

        current_eps = earnings_data.get(
            "current_eps",
            0
        )

        previous_eps = earnings_data.get(
            "previous_eps",
            0
        )

        current_revenue = earnings_data.get(
            "current_revenue",
            0
        )

        previous_revenue = earnings_data.get(
            "previous_revenue",
            0
        )

        avg_surprise = earnings_data.get(
            "avg_surprise_percent",
            0
        )

        # ==========================
        # Growth Calculations
        # ==========================
        eps_growth = calculate_growth(
            current_eps,
            previous_eps
        )

        revenue_growth = calculate_growth(
            current_revenue,
            previous_revenue
        )

        days_to_earnings = get_days_to_earnings(
            earnings_date
        )

        # ==========================
        # EPS Growth
        # ==========================
        if eps_growth >= 20:

            score += 15

            reasons.append(
                "Strong EPS Growth"
            )

        elif eps_growth >= 10:

            score += 10

            reasons.append(
                "Healthy EPS Growth"
            )

        # ==========================
        # Revenue Growth
        # ==========================
        if revenue_growth >= 15:

            score += 15

            reasons.append(
                "Strong Revenue Growth"
            )

        elif revenue_growth >= 8:

            score += 10

            reasons.append(
                "Healthy Revenue Growth"
            )

        # ==========================
        # Earnings Surprise
        # ==========================
        if avg_surprise >= 10:

            score += 10

            reasons.append(
                "Consistent Earnings Beat"
            )

        elif avg_surprise < 0:

            score -= 10

            reasons.append(
                "Frequent Earnings Miss"
            )

        # ==========================
        # Earnings Risk Window
        # ==========================
        if days_to_earnings is not None:

            if 0 <= days_to_earnings <= 5:

                score -= 15

                reasons.append(
                    "Earnings Near High Risk"
                )

            elif 5 < days_to_earnings <= 15:

                score -= 5

                reasons.append(
                    "Earnings Approaching"
                )

        return {
            "score": score,
            "reason": ", ".join(reasons),
            "raw": {
                "eps_growth": round(
                    eps_growth, 2
                ),
                "revenue_growth": round(
                    revenue_growth, 2
                ),
                "days_to_earnings": days_to_earnings
            }
        }

    except Exception as e:

        logger.error(
            f"Earnings failed: {e}"
        )

        return {
            "score": 0,
            "reason": "Earnings Error",
            "raw": {}
        }