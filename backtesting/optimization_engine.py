from utils.logger import logger

from backtesting.strategy_tester import (
    run_strategy_test
)

import pandas as pd


def optimize_strategy(
    df,
    strategy_func,
    score_thresholds=None,
    holding_periods=None
):
    """
    Strategy Parameter Optimization Engine
    """

    try:

        if score_thresholds is None:

            score_thresholds = [
                40, 50, 60, 70
            ]

        if holding_periods is None:

            holding_periods = [
                3, 5, 10
            ]

        all_results = []

        for threshold in score_thresholds:

            for holding in holding_periods:

                result = run_strategy_test(
                    df=df,
                    strategy_func=strategy_func,
                    score_threshold=threshold,
                    holding_period=holding
                )

                metrics = result["metrics"]

                all_results.append({
                    "score_threshold":
                        threshold,

                    "holding_period":
                        holding,

                    **metrics
                })

        results_df = pd.DataFrame(
            all_results
        )

        # ==========================
        # Sort by Profit Factor
        # ==========================
        results_df = results_df.sort_values(
            by="profit_factor",
            ascending=False
        )

        return results_df

    except Exception as e:

        logger.error(
            f"Optimization failed: {e}"
        )

        return pd.DataFrame()