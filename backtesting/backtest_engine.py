import pandas as pd


def run_backtest(
    df,
    strategy_func,
    score_threshold=50,
    holding_period=5
):
    """
    Basic backtesting engine
    """

    trades = []

    for i in range(50, len(df) - holding_period):

        historical_df = df.iloc[:i]

        result = strategy_func(
            historical_df
        )

        score = float(result.get("score", 0) or 0)
        if abs(score) >= score_threshold:

            entry_price = df[
                "Open"
            ].iloc[i + 1]

            exit_price = df[
                "Close"
            ].iloc[
                i + holding_period
            ]

            if score >= 0:
                pnl = (
                    (
                        exit_price -
                        entry_price
                    ) / entry_price
                ) * 100
                direction = "LONG"
            else:
                pnl = (
                    (
                        entry_price -
                        exit_price
                    ) / entry_price
                ) * 100
                direction = "SHORT"

            trades.append({
                "entry_date": df.index[i + 1],
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl": pnl,
                "score": score,
                "direction": direction
            })

    return pd.DataFrame(trades)
