from utils.logger import logger
import pandas as pd


def rank_stocks(
    stock_results,
    min_score=20,
    min_confidence=50,
    top_n=10,
    strict_shortlist=False,
    min_expected_return_pct=0,
    min_ml_probability=None,
    min_risk_reward=None,
    max_stop_distance_pct=None,
    min_data_reliability_score=None,
    min_profitability_score=None,
):
    """
    Advanced Ranking Engine
    """

    try:

        if not stock_results:

            return pd.DataFrame()

        df = pd.DataFrame(
            stock_results
        )
        if "quality_filter_passed" in df.columns:
            df = df[df["quality_filter_passed"].fillna(False)]

        if df.empty:
            return pd.DataFrame()

        defaults = {
            "score": 0,
            "confidence_pct": 0,
            "profitability_score": 0,
            "ml_probability": 0,
            "profit_factor": 0,
            "backtest_win_rate": 0,
            "premarket_grade": 0,
            "risk_reward": 0,
            "stop_distance_pct": 0,
            "expected_return": 0,
            "data_reliability_score": 0,
            "risk_level": "Unknown",
            "premarket_status": "Rejected",
            "quality_score": 0,
            "walk_forward_profit_factor": 0,
            "walk_forward_segments": 0,
            "trade_type": "",
            "optimized_profit_factor": 0,
            "walk_forward_win_rate": 0,
            "max_drawdown": 0,
            "walk_forward_max_drawdown": 0,
        }
        for column, default in defaults.items():
            if column not in df.columns:
                df[column] = default

        min_ml = 60 if strict_shortlist else 50
        if min_ml_probability is not None:
            min_ml = max(min_ml, float(min_ml_probability))
        min_rr = 1.4 if strict_shortlist else 1.15
        if min_risk_reward is not None:
            min_rr = max(min_rr, float(min_risk_reward))
        max_stop = 5 if strict_shortlist else 8
        if max_stop_distance_pct is not None:
            max_stop = min(max_stop, float(max_stop_distance_pct))
        min_data = 35 if strict_shortlist else 15
        if min_data_reliability_score is not None:
            min_data = max(min_data, float(min_data_reliability_score))
        min_profitability = 15 if strict_shortlist else 8
        if min_profitability_score is not None:
            min_profitability = max(min_profitability, float(min_profitability_score))

        # ==========================
        # Apply Filters
        # ==========================
        primary_df = df[
            (
                df["score"].abs() >= max(min_score, 15)
            ) &
            (
                df["confidence_pct"] >= max(min_confidence, 50)
            ) &
            (
                df.get("profitability_score", 0) >= min_profitability
            ) &
            (
                df.get("ml_probability", 0) >= min_ml
            ) &
            (
                (
                    df.get("profit_factor", 0) >= 1
                ) |
                (
                    df.get("backtest_win_rate", 0) >= 60
                )
            ) &
            (
                df.get("premarket_grade", 0) >= 45
            ) &
            (
                df.get("risk_reward", 0) >= min_rr
            ) &
            (
                df.get("stop_distance_pct", 0) <= max_stop
            ) &
            (
                df.get("data_reliability_score", 0) >= min_data
            ) &
            (
                df.get("expected_return", 0) >= float(min_expected_return_pct or 0)
            ) &
            (
                df.get("risk_level", "Unknown").isin(["Low", "Medium"])
            ) &
            (
                df.get("premarket_status", "Watchlist") != "Rejected"
            )
        ]

        if primary_df.empty and not strict_shortlist:
            primary_df = df[
                (
                    df["score"].abs() >= max(min_score - 3, 12)
                ) &
                (
                    df["confidence_pct"] >= max(min_confidence - 3, 47)
                ) &
                (
                    df.get("profitability_score", 0) > 0
                ) &
                (
                    df.get("ml_probability", 0) >= min_ml
                )
                &
                (
                    df.get("premarket_grade", 0) >= 35
                )
                &
                (
                    df.get("stop_distance_pct", 0) <= max_stop
                )
                &
                (
                    df.get("data_reliability_score", 0) >= min_data
                )
                &
                (
                    df.get("expected_return", 0) >= float(min_expected_return_pct or 0)
                )
                &
                (
                    df.get("risk_level", "Unknown").isin(["Low", "Medium"])
                )
            ]

        df = primary_df

        if df.empty:
            return pd.DataFrame()

        if strict_shortlist:
            df = df[
                (
                    df.get("ml_probability", 0) >= min_ml
                ) &
                (
                    df.get("profitability_score", 0) >= min_profitability
                ) &
                (
                    df.get("quality_score", 0) >= 58
                ) &
                (
                    df.get("premarket_grade", 0) >= 58
                ) &
                (
                    df.get("risk_reward", 0) >= min_rr
                ) &
                (
                    df.get("stop_distance_pct", 0) <= max_stop
                ) &
                (
                    df.get("data_reliability_score", 0) >= min_data
                ) &
                (
                    df.get("expected_return", 0) >= float(min_expected_return_pct or 0)
                ) &
                (
                    df.get("profit_factor", 0) >= 1.2
                ) &
                (
                    (
                        df.get("walk_forward_profit_factor", 0) >= 1
                    ) |
                    (
                        df.get("walk_forward_segments", 0) == 0
                    )
                ) &
                (
                    df["trade_type"].isin(["BUY", "SELL", "BUY WATCH", "SELL WATCH"])
                )
                &
                (
                    df.get("premarket_status", "") == "Qualified"
                )
            ]

            if df.empty:
                return pd.DataFrame()

        # ==========================
        # Combined Ranking Metric
        # ==========================
        df["ranking_score"] = (
            (
                df["score"].abs() * 0.35
            ) +
            (
                df["confidence_pct"] * 0.15
            ) +
            (
                df.get("ml_probability", 0) * 0.18
            ) +
            (
                df.get("premarket_grade", 0) * 0.18
            ) +
            (
                df["profitability_score"] * 0.3
            ) +
            (
                df.get("expected_return", 0) * 0.45
            ) +
            (
                df.get("quality_score", 0) * 0.10
            ) +
            (
                df.get("data_reliability_score", 0) * 0.08
            ) +
            (
                df["profit_factor"] * 8
            ) +
            (
                df.get("optimized_profit_factor", 0) * 3
            ) +
            (
                df["backtest_win_rate"] * 0.08
            ) +
            (
                df.get("walk_forward_win_rate", 0) * 0.05
            ) +
            (
                df.get("walk_forward_profit_factor", 0) * 4
            ) -
            (
                df.get("max_drawdown", 0) * 0.1
            ) -
            (
                df.get("walk_forward_max_drawdown", 0) * 0.05
            )
        )

        # ==========================
        # Sort Descending
        # ==========================
        df = df.sort_values(
            by="ranking_score",
            ascending=False
        )

        # ==========================
        # Assign Rank Number
        # ==========================
        df["rank"] = range(
            1,
            len(df) + 1
        )

        # ==========================
        # Keep Top N
        # ==========================
        df = df.head(top_n)

        return df

    except Exception as e:

        logger.error(
            f"Ranking failed: {e}"
        )

        return pd.DataFrame()
