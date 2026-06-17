import math

import pandas as pd

from utils.logger import logger


def calculate_metrics(trades_df):
    """
    Calculate basic backtest performance metrics.
    """

    try:
        if trades_df is None or trades_df.empty:
            return {
                "trades": 0,
                "win_rate": 0,
                "avg_pnl": 0,
                "profit_factor": 0,
                "expectancy": 0,
                "max_drawdown": 0,
                "sharpe_like": 0,
            }

        pnl = pd.to_numeric(trades_df["pnl"], errors="coerce").dropna()
        if pnl.empty:
            return {
                "trades": 0,
                "win_rate": 0,
                "avg_pnl": 0,
                "profit_factor": 0,
                "expectancy": 0,
                "max_drawdown": 0,
                "sharpe_like": 0,
            }

        wins = pnl[pnl > 0]
        losses = pnl[pnl <= 0]
        gross_profit = wins.sum()
        gross_loss = abs(losses.sum())
        profit_factor = gross_profit / gross_loss if gross_loss else gross_profit

        equity_curve = (1 + (pnl / 100)).cumprod()
        rolling_peak = equity_curve.cummax()
        drawdowns = ((equity_curve / rolling_peak) - 1) * 100

        std = pnl.std()
        sharpe_like = (pnl.mean() / std) * math.sqrt(len(pnl)) if std else 0

        return {
            "trades": int(len(pnl)),
            "win_rate": round((len(wins) / len(pnl)) * 100, 2),
            "avg_pnl": round(pnl.mean(), 2),
            "profit_factor": round(profit_factor, 2),
            "expectancy": round(pnl.mean(), 2),
            "max_drawdown": round(abs(drawdowns.min()), 2),
            "sharpe_like": round(sharpe_like, 2),
        }

    except Exception as exc:
        logger.error(f"Performance metrics failed: {exc}")
        return {
            "trades": 0,
            "win_rate": 0,
            "avg_pnl": 0,
            "profit_factor": 0,
            "expectancy": 0,
            "max_drawdown": 0,
            "sharpe_like": 0,
        }
