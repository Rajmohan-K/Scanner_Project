from utils.logger import logger

from backtesting.strategy_tester import (
    run_strategy_test
)
from backtesting.performance_metrics import (
    calculate_metrics
)

import pandas as pd


def run_walk_forward(
    df,
    strategy_func,
    train_window=100,
    test_window=20,
    score_threshold=50
):
    """
    Walk Forward Validation Engine
    """

    try:

        all_results = []

        start = train_window

        while start + test_window < len(df):

            # ==========================
            # Train/Test Split
            # ==========================
            train_df = df.iloc[
                start - train_window:start
            ]

            test_df = df.iloc[
                start:start + test_window
            ]
            combined_df = df.iloc[
                start - train_window:start + test_window
            ]

            # ==========================
            # Test Strategy
            # ==========================
            result = run_strategy_test(
                df=combined_df,
                strategy_func=strategy_func,
                score_threshold=score_threshold
            )

            trades_df = result.get("trades")
            if trades_df is None or trades_df.empty:
                metrics = {}
            else:
                test_start_date = test_df.index[0]
                filtered_trades = trades_df[
                    trades_df["entry_date"] >= test_start_date
                ]
                metrics = calculate_metrics(filtered_trades)

            all_results.append({
                "train_start":
                    train_df.index[0],

                "train_end":
                    train_df.index[-1],

                "test_start":
                    test_df.index[0],

                "test_end":
                    test_df.index[-1],

                **metrics
            })

            start += test_window

        return pd.DataFrame(
            all_results
        )

    except Exception as e:

        logger.error(
            f"Walk forward failed: {e}"
        )

        return pd.DataFrame()
