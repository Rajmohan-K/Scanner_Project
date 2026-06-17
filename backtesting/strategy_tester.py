from utils.logger import logger

from backtesting.backtest_engine import (
    run_backtest
)

from backtesting.performance_metrics import (
    calculate_metrics
)


def run_strategy_test(
    df,
    strategy_func,
    score_threshold=50,
    holding_period=5
):
    """
    Master Strategy Testing Engine
    """

    try:

        # ==========================
        # Run Backtest
        # ==========================
        trades_df = run_backtest(
            df=df,
            strategy_func=strategy_func,
            score_threshold=score_threshold,
            holding_period=holding_period
        )

        # ==========================
        # Generate Metrics
        # ==========================
        metrics = calculate_metrics(
            trades_df
        )

        result = {
            "metrics": metrics,
            "trades": trades_df
        }

        return result

    except Exception as e:

        logger.error(
            f"Strategy tester failed: {e}"
        )

        return {
            "metrics": {},
            "trades": None
        }