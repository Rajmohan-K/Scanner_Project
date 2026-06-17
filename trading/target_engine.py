from utils.logger import logger
from utils.helpers import calculate_risk_reward, round_dict


def generate_targets(
    df,
    signal,
    score=0,
    live_price=None,
    expected_open=None,
):
    """
    Generate trade targets
    based on recent swing highs/lows.
    """

    try:

        current_price = float(df[
            "Close"
        ].iloc[-1])

        recent_high = float(df[
            "High"
        ].tail(10).max())

        recent_low = float(df[
            "Low"
        ].tail(10).min())

        latest_open = float(df[
            "Open"
        ].iloc[-1])

        previous_close = float(df[
            "Close"
        ].iloc[-2]) if len(df) >= 2 else current_price

        gap_percent = (
            (
                latest_open - previous_close
            ) / previous_close
        ) * 100 if previous_close else 0

        reference_live_price = (
            round(float(live_price), 2)
            if isinstance(live_price, (int, float))
            else round(current_price, 2)
        )

        expected_open_price = (
            round(float(expected_open), 2)
            if isinstance(expected_open, (int, float))
            else round(reference_live_price, 2)
        )

        result = {}

        is_long_setup = (
            "BUY" in signal or
            (
                "SELL" not in signal and
                score >= 0
            )
        )

        setup_type = (
            "LONG"
            if "BUY" in signal
            else "SHORT"
            if "SELL" in signal
            else "LONG WATCH"
            if is_long_setup
            else "SHORT WATCH"
        )

        # ==========================
        # Long setup
        # ==========================
        if is_long_setup:

            entry = expected_open_price or reference_live_price or current_price

            stoploss = recent_low

            risk = (
                entry - stoploss
            )

            if risk <= 0:

                stoploss = round(entry * 0.98, 2)
                risk = entry - stoploss

            target1 = (
                entry + risk
            )

            target2 = (
                entry + (risk * 2)
            )

            rr = calculate_risk_reward(
                entry,
                stoploss,
                target2,
            )
            stop_distance_pct = (risk / entry) * 100 if entry else 0

            result = round_dict({
                "setup_type": setup_type,
                "live_price": reference_live_price,
                "expected_open": expected_open_price,
                "entry":
                    round(entry, 2),

                "stoploss":
                    round(stoploss, 2),

                "target1":
                    round(target1, 2),

                "target2":
                    round(target2, 2),

                "risk_reward":
                    round(rr, 2),

                "stop_distance_pct":
                    round(stop_distance_pct, 2)
            })

        # ==========================
        # Short setup
        # ==========================
        else:

            entry = expected_open_price or reference_live_price or current_price

            stoploss = recent_high

            risk = (
                stoploss - entry
            )

            if risk <= 0:

                stoploss = round(entry * 1.02, 2)
                risk = stoploss - entry

            target1 = (
                entry - risk
            )

            target2 = (
                entry - (risk * 2)
            )

            rr = calculate_risk_reward(
                entry,
                stoploss,
                target2,
            )
            stop_distance_pct = (risk / entry) * 100 if entry else 0

            result = round_dict({
                "setup_type": setup_type,
                "live_price": reference_live_price,
                "expected_open": expected_open_price,
                "entry":
                    round(entry, 2),

                "stoploss":
                    round(stoploss, 2),

                "target1":
                    round(target1, 2),

                "target2":
                    round(target2, 2),

                "risk_reward":
                    round(rr, 2),

                "stop_distance_pct":
                    round(stop_distance_pct, 2)
            })

        result["gap_percent"] = round(gap_percent, 2)

        return result

    except Exception as e:

        logger.error(
            f"Target engine failed: {e}"
        )

        return {}
