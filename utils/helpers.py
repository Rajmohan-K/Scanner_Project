from utils.logger import logger


def safe_divide(
    numerator,
    denominator,
    default=0
):
    """
    Prevent divide-by-zero errors.
    """

    try:

        if denominator == 0:

            return default

        return numerator / denominator

    except Exception as e:

        logger.error(
            f"Safe divide failed: {e}"
        )

        return default


def calculate_pct_change(
    old,
    new
):
    """
    Calculate percentage change.
    """

    try:

        return safe_divide(
            (
                new - old
            ) * 100,
            old
        )

    except Exception as e:

        logger.error(
            f"Pct change failed: {e}"
        )

        return 0


def normalize_value(
    value,
    min_val,
    max_val
):
    """
    Normalize value between 0-100.
    """

    try:

        return (
            (
                value - min_val
            ) /
            (
                max_val - min_val
            )
        ) * 100

    except Exception as e:

        logger.error(
            f"Normalize failed: {e}"
        )

        return 0


def validate_dataframe(
    df,
    min_rows=20
):
    """
    Validate dataframe quality.
    """

    try:

        if df is None:

            return False

        if df.empty:

            return False

        if len(df) < min_rows:

            return False

        required_cols = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume"
        ]

        for col in required_cols:

            if col not in df.columns:

                return False

        return True

    except Exception as e:

        logger.error(
            f"Validation failed: {e}"
        )

        return False


def calculate_risk_reward(
    entry,
    stoploss,
    target
):
    """
    Calculate RR ratio.
    """

    try:

        risk = abs(
            entry - stoploss
        )

        reward = abs(
            target - entry
        )

        return safe_divide(
            reward,
            risk
        )

    except Exception as e:

        logger.error(
            f"RR calc failed: {e}"
        )

        return 0


def round_dict(
    data,
    decimals=2
):
    """
    Round numeric dict values.
    """

    try:

        return {

            k: round(v, decimals)
            if isinstance(
                v,
                (
                    int,
                    float
                )
            )
            else v

            for k, v in data.items()
        }

    except Exception as e:

        logger.error(
            f"Round dict failed: {e}"
        )

        return data