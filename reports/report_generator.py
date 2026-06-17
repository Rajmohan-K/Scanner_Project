from utils.logger import logger
from reports.excel_export import (
    export_to_excel
)
import pandas as pd


REPORT_COLUMNS = {
    "Stock": ("stock", "Stock"),
    "Sector": ("sector", "Sector"),
    "Live Price": ("live_price", "Live Price"),
    "Last Close": ("last_close", "Last Close"),
    "Open": ("open", "Open"),
    "High": ("high", "High"),
    "Low": ("low", "Low"),
    "Volume": ("volume", "Volume"),
    "Data Timestamp": ("data_timestamp", "Data Timestamp"),
    "Score": ("score", "Score", "coarse_score", "Coarse Score"),
    "Technical Score": ("technical_score", "Technical Score"),
    "Fundamental Score": ("fundamental_score", "Fundamental Score"),
    "Fundamental Source": ("fundamental_source", "Fundamental Source"),
    "Fundamental Data Quality": ("fundamental_data_quality", "Fundamental Data Quality"),
    "Volume Strength": ("volume_strength", "Volume Strength"),
    "Breakout Strength": ("breakout_strength", "Breakout Strength"),
    "Momentum Score": ("momentum_score", "Momentum Score"),
    "Trend Score": ("trend_score", "Trend Score"),
    "Liquidity Score": ("liquidity_score", "Liquidity Score"),
    "Market Strength Score": ("market_strength_score", "Market Strength Score"),
    "Sector Strength Score": ("sector_strength_score", "Sector Strength Score"),
    "Confidence": ("confidence_pct", "Confidence", "coarse_confidence", "Coarse Confidence"),
    "Coarse Quality": ("coarse_quality", "Coarse Quality"),
    "Coarse Risk": ("coarse_risk", "Coarse Risk"),
    "Profitability Score": ("profitability_score", "Profitability Score"),
    "Quality Score": ("quality_score", "Quality Score"),
    "Data Reliability Score": ("data_reliability_score", "Data Reliability Score"),
    "ML Probability": ("ml_probability", "ML Probability"),
    "Premarket Grade": ("premarket_grade", "Premarket Grade"),
    "Premarket Status": ("premarket_status", "Premarket Status"),
    "Premarket Action": ("premarket_action", "Premarket Action"),
    "Best Horizon": ("best_horizon", "Best Horizon"),
    "Market Context Score": ("market_context_score", "Market Context Score"),
    "Event Score": ("event_score", "Event Score"),
    "Event Reason": ("event_reason", "Event Reason"),
    "Delivery Source": ("delivery_source", "Delivery Source"),
    "Delivery Data Quality": ("delivery_data_quality", "Delivery Data Quality"),
    "Insider Source": ("insider_source", "Insider Source"),
    "Insider Data Quality": ("insider_data_quality", "Insider Data Quality"),
    "Options Source": ("options_source", "Options Source"),
    "Options Data Quality": ("options_data_quality", "Options Data Quality"),
    "Earnings Date": ("earnings_date", "Earnings Date"),
    "Days To Earnings": ("days_to_earnings", "Days To Earnings"),
    "Block Deal Count": ("block_deal_count", "Block Deal Count"),
    "Geopolitical Headlines": ("geopolitical_headlines", "Geopolitical Headlines"),
    "FII Source": ("fii_source", "FII Source"),
    "Backtest Win Rate": ("backtest_win_rate", "Backtest Win Rate"),
    "Profit Factor": ("profit_factor", "Profit Factor"),
    "Walk Forward Win Rate": ("walk_forward_win_rate", "Walk Forward Win Rate"),
    "Walk Forward Profit Factor": ("walk_forward_profit_factor", "Walk Forward Profit Factor"),
    "Optimized Score Threshold": ("optimized_score_threshold", "Optimized Score Threshold"),
    "Optimized Holding Period": ("optimized_holding_period", "Optimized Holding Period"),
    "Optimized Win Rate": ("optimized_win_rate", "Optimized Win Rate"),
    "Optimized Profit Factor": ("optimized_profit_factor", "Optimized Profit Factor"),
    "Max Drawdown": ("max_drawdown", "Max Drawdown"),
    "Risk": ("risk_level", "Risk"),
    "Risk Score": ("risk_score", "Risk Score"),
    "Risk Reason": ("risk_reason", "Risk Reason"),
    "Recommended Risk %": ("recommended_risk_pct", "Recommended Risk %"),
    "Position Size": ("position_size", "Position Size"),
    "Expected Return": ("expected_return", "Expected Return"),
    "Final Opportunity Score": ("final_opportunity_score", "Final Opportunity Score"),
    "Opportunity Classification": ("opportunity_classification", "Opportunity Classification"),
    "Regime": ("regime", "Regime"),
    "Trend Regime": ("trend_regime", "Trend Regime"),
    "Volatility Regime": ("volatility_regime", "Volatility Regime"),
    "Signal": ("signal", "Signal"),
    "Trade Type": ("trade_type", "Trade Type"),
    "Trade Reason": ("trade_reason", "Trade Reason"),
    "Setup Type": ("setup_type", "Setup Type"),
    "Expected Open": ("expected_open", "Expected Open"),
    "Entry": ("entry", "Entry"),
    "Stoploss": ("stoploss", "Stoploss"),
    "Target1": ("target1", "Target1"),
    "Target2": ("target2", "Target2"),
    "Risk Reward": ("risk_reward", "Risk Reward"),
    "Stop Distance %": ("stop_distance_pct", "Stop Distance %"),
    "Gap %": ("gap_percent", "Gap %"),
}


def _value(stock, *keys, default=""):
    for key in keys:
        if key in stock and stock.get(key) is not None:
            return stock.get(key)
    return default


def _float_value(stock, *keys, default=0.0):
    try:
        return float(_value(stock, *keys, default=default) or default)
    except (TypeError, ValueError):
        return default


def _scan_mode_text(scan_mode):
    return str(scan_mode or "").strip().lower().replace("_", "-")


def _is_intraday_scan(scan_mode):
    mode = _scan_mode_text(scan_mode)
    return "intraday" in mode or "premarket" in mode or "market-open" in mode


def _is_swing_scan(scan_mode):
    return "swing" in _scan_mode_text(scan_mode)


def _derive_action_signal(stock):
    premarket_action = str(_value(stock, "premarket_action", "Premarket Action", default="") or "").upper()
    if premarket_action in ["BUY", "SELL"]:
        return premarket_action

    score = float(_value(stock, "score", "Score", default=0) or 0)
    confidence = float(_value(stock, "confidence_pct", "Confidence", default=0) or 0)
    ml_probability = float(_value(stock, "ml_probability", "ML Probability", default=0) or 0)
    quality_score = float(_value(stock, "quality_score", "Quality Score", default=0) or 0)
    profitability_score = float(_value(stock, "profitability_score", "Profitability Score", default=0) or 0)
    trade_type = str(_value(stock, "trade_type", "Trade Type", default="") or "").upper()
    setup_type = str(_value(stock, "setup_type", "Setup Type", default="") or "").upper()

    is_buy_side = "BUY" in trade_type or "LONG" in setup_type or score > 0
    is_sell_side = "SELL" in trade_type or "SHORT" in setup_type or score < 0

    if (
        is_buy_side and
        score >= 15 and
        confidence >= 65 and
        ml_probability >= 85 and
        quality_score >= 90 and
        profitability_score >= 70
    ):
        return "BUY"

    if (
        is_sell_side and
        score <= -15 and
        confidence >= 65 and
        ml_probability >= 85 and
        quality_score >= 90 and
        profitability_score >= 70
    ):
        return "SELL"

    return ""


def _derive_report_action(stock, scan_mode=None):
    direct = str(_value(
        stock,
        "premarket_action",
        "action",
        "ai_rating",
        "recommendation",
        "signal",
        "trade_type",
        default="",
    ) or "").upper()
    if any(token in direct for token in ("STRONG BUY", "BUY", "LONG")):
        return "BUY"
    if any(token in direct for token in ("SELL", "SHORT")):
        return "SELL"
    if any(token in direct for token in ("AVOID", "HOLD", "WATCH")):
        return direct

    score = _float_value(stock, "score", "technical_score", "final_ai_score", default=0)
    confidence = _float_value(stock, "confidence_pct", "confidence", default=0)
    ml_probability = _float_value(stock, "ml_probability", "ml_score", default=0)
    expected_return = _float_value(stock, "expected_return", default=0)
    risk_reward = _float_value(stock, "risk_reward", "rrr", default=0)

    if _is_intraday_scan(scan_mode):
        if ml_probability >= 60 or confidence >= 55 or score >= 12 or expected_return >= 1.5:
            return "BUY"
    if _is_swing_scan(scan_mode):
        if risk_reward >= 1.5 or expected_return >= 4 or ml_probability >= 58 or confidence >= 55:
            return "BUY"
    if ml_probability >= 60 or confidence >= 60 or score >= 15:
        return "BUY"
    return "WATCH"


def _derive_horizon(stock):
    best_horizon = str(_value(stock, "best_horizon", "Best Horizon", default="") or "")
    if best_horizon in ["Intraday", "Swing"]:
        return "Intraday" if best_horizon == "Intraday" else "Swing 1-2 Days"

    gap_pct = abs(float(_value(stock, "gap_percent", "Gap %", default=0) or 0))
    volatility_regime = str(_value(stock, "volatility_regime", "Volatility Regime", default="") or "")
    optimized_holding = float(_value(stock, "optimized_holding_period", "Optimized Holding Period", default=0) or 0)

    if (
        gap_pct >= 2 or
        volatility_regime in ["High Vol", "Extreme Vol"] or
        (optimized_holding and optimized_holding <= 3)
    ):
        return "Intraday"

    return "Swing 1-2 Days"


def _derive_report_category(stock, scan_mode=None):
    if _is_intraday_scan(scan_mode):
        return "Intraday"
    if _is_swing_scan(scan_mode):
        return "Swing 1-2 Days"
    return _derive_horizon(stock)


def _build_clear_reason(stock):
    reason = str(_value(stock, "trade_reason", "Trade Reason", default="") or "").strip()
    parts = [part.strip() for part in reason.split("|") if part.strip()]
    short_reason = " | ".join(parts[:3])
    metrics = (
        f"ML {_value(stock, 'ml_probability', 'ML Probability', default=0)} | "
        f"Conf {_value(stock, 'confidence_pct', 'Confidence', default=0)} | "
        f"PF {_value(stock, 'profit_factor', 'Profit Factor', default=0)} | "
        f"PreM {_value(stock, 'premarket_grade', 'Premarket Grade', default=0)} | "
        f"Event {_value(stock, 'event_score', 'Event Score', default=0)}"
    )
    return f"{short_reason} | {metrics}" if short_reason else metrics


def build_clear_trade_report(ranked_results):
    clear_rows = []

    for stock in ranked_results:
        action_signal = _derive_action_signal(stock)
        if not action_signal:
            continue

        clear_rows.append({
            "Category": _derive_horizon(stock),
            "Action": action_signal,
            "Stock": _value(stock, "stock", "Stock"),
            "Live Price": _value(stock, "live_price", "Live Price"),
            "Expected Open": _value(stock, "expected_open", "Expected Open"),
            "Entry": _value(stock, "entry", "Entry"),
            "Stoploss": _value(stock, "stoploss", "Stoploss"),
            "Target1": _value(stock, "target1", "Target1"),
            "Target2": _value(stock, "target2", "Target2"),
            "Risk Reward": _value(stock, "risk_reward", "Risk Reward"),
            "Stop Distance %": _value(stock, "stop_distance_pct", "Stop Distance %"),
            "Score": _value(stock, "score", "Score"),
            "Confidence": _value(stock, "confidence_pct", "Confidence"),
            "ML Probability": _value(stock, "ml_probability", "ML Probability"),
            "Profitability Score": _value(stock, "profitability_score", "Profitability Score"),
            "Profit Factor": _value(stock, "profit_factor", "Profit Factor"),
            "Premarket Grade": _value(stock, "premarket_grade", "Premarket Grade"),
            "Premarket Status": _value(stock, "premarket_status", "Premarket Status"),
            "Best Horizon": _value(stock, "best_horizon", "Best Horizon"),
            "Event Score": _value(stock, "event_score", "Event Score"),
            "Regime": _value(stock, "regime", "Regime"),
            "Reason": _build_clear_reason(stock),
        })

    if not clear_rows:
        return {
            "Best_Stocks": pd.DataFrame(columns=[
                "Category", "Action", "Stock", "Live Price", "Expected Open",
                "Entry", "Stoploss", "Target1", "Target2", "Risk Reward",
                "Score", "Confidence", "ML Probability", "Profitability Score",
                "Profit Factor", "Premarket Grade", "Premarket Status",
                "Best Horizon", "Event Score", "Regime", "Reason"
            ]),
            "Intraday": pd.DataFrame(),
            "Swing_1_2_Days": pd.DataFrame(),
        }

    clear_df = pd.DataFrame(clear_rows).sort_values(
        by=["ML Probability", "Profitability Score", "Confidence", "Score"],
        ascending=False,
    )

    return {
        "Best_Stocks": clear_df,
        "Intraday": clear_df[clear_df["Category"] == "Intraday"],
        "Swing_1_2_Days": clear_df[clear_df["Category"] == "Swing 1-2 Days"],
    }


def _sort_report_rows(rows):
    if not rows:
        return rows
    df = pd.DataFrame(rows)
    sort_columns = [
        column
        for column in [
            "Report Score",
            "ML Probability",
            "Expected Return",
            "Risk Reward",
            "Profitability Score",
            "Confidence",
            "Score",
        ]
        if column in df.columns
    ]
    if sort_columns:
        df = df.sort_values(by=sort_columns, ascending=False)
    df.insert(0, "Rank", range(1, len(df) + 1))
    return df.to_dict(orient="records")


def build_scan_type_report(candidate_results, scan_mode=None):
    rows = []
    for stock in candidate_results or []:
        category = _derive_report_category(stock, scan_mode)
        ml_probability = _float_value(stock, "ml_probability", "ML Probability", default=0)
        confidence = _float_value(stock, "confidence_pct", "Confidence", default=0)
        expected_return = _float_value(stock, "expected_return", "Expected Return", default=0)
        risk_reward = _float_value(stock, "risk_reward", "Risk Reward", default=0)
        profitability = _float_value(stock, "profitability_score", "Profitability Score", default=0)
        technical = _float_value(stock, "technical_score", "Technical Score", "score", "Score", default=0)
        data_quality = _float_value(stock, "data_reliability_score", "Data Reliability Score", default=0)
        report_score = (
            ml_probability * 0.28
            + confidence * 0.18
            + profitability * 0.18
            + technical * 0.16
            + max(expected_return, 0) * 1.2
            + min(max(risk_reward, 0), 5) * 4
            + data_quality * 0.08
        )
        rows.append({
            "Category": category,
            "Action": _derive_report_action(stock, scan_mode),
            "Stock": _value(stock, "stock", "symbol", "Stock"),
            "Sector": _value(stock, "sector", "Sector"),
            "Industry": _value(stock, "industry", "Industry"),
            "Live Price": _value(stock, "live_price", "current_price", "Live Price"),
            "Entry": _value(stock, "entry", "entry_price", "Entry"),
            "Stoploss": _value(stock, "stoploss", "stop_loss", "Stoploss"),
            "Target1": _value(stock, "target1", "target_1", "Target1"),
            "Target2": _value(stock, "target2", "target_2", "Target2"),
            "Risk Reward": risk_reward,
            "Stop Distance %": _value(stock, "stop_distance_pct", "Stop Distance %"),
            "Expected Return": expected_return,
            "Report Score": round(report_score, 2),
            "Score": _value(stock, "score", "Score"),
            "Technical Score": technical,
            "Confidence": confidence,
            "ML Probability": ml_probability,
            "Profitability Score": profitability,
            "Data Reliability Score": data_quality,
            "Best Horizon": _value(stock, "best_horizon", "Best Horizon", default=category),
            "Pattern": _value(stock, "pattern", "setup_type", "Setup Type"),
            "Reason": _build_clear_reason(stock),
        })

    sorted_rows = _sort_report_rows(rows)
    report_df = pd.DataFrame(sorted_rows)
    if report_df.empty:
        report_df = pd.DataFrame(columns=[
            "Rank", "Category", "Action", "Stock", "Sector", "Live Price",
            "Entry", "Stoploss", "Target1", "Target2", "Risk Reward",
            "Expected Return", "Report Score", "Reason",
        ])
    intraday_df = report_df[report_df["Category"] == "Intraday"].copy() if "Category" in report_df else pd.DataFrame()
    swing_df = report_df[report_df["Category"] == "Swing 1-2 Days"].copy() if "Category" in report_df else pd.DataFrame()
    return {
        "Best_Stocks": report_df,
        "Intraday": intraday_df,
        "Swing_1_2_Days": swing_df,
    }


def _market_open_value(stock, *path, default=None):
    value = stock
    for key in path:
        if not isinstance(value, dict):
            return default
        value = value.get(key)
    return default if value is None else value


def build_report_dataframe(results):
    rows = []
    for stock in results or []:
        row = {
            column: _value(stock, *keys)
            for column, keys in REPORT_COLUMNS.items()
        }
        row.update({
            "Market Open Price": _market_open_value(stock, "market_open_analysis", "market_open_price"),
            "Price At 09:08": _market_open_value(stock, "market_open_analysis", "price_at_target_time"),
            "Market Open Strength": _market_open_value(stock, "market_open_validation", "opening_strength_pct"),
            "Order Flow Strength": _market_open_value(stock, "market_open_validation", "order_flow_strength"),
            "Buy/Sell Pressure": _market_open_value(stock, "market_open_validation", "buy_sell_pressure"),
            "Final Trade Quality Score": _market_open_value(stock, "market_open_validation", "final_trade_quality_score"),
            "Market Open Opportunity Classification": _market_open_value(stock, "market_open_validation", "opportunity_classification"),
            "Premarket Confidence Score": _market_open_value(stock, "market_open_validation", "premarket_confidence_score"),
            "Open Confirmation Score": _market_open_value(stock, "market_open_validation", "market_open_confirmation_score"),
            "Price Acceptance Above Key Levels": _market_open_value(stock, "market_open_validation", "price_acceptance_above_key_levels"),
            "Price Rejection Below Key Levels": _market_open_value(stock, "market_open_validation", "price_rejection_below_key_levels"),
            "Relative Volume Increase": _market_open_value(stock, "market_open_validation", "relative_volume_increase"),
            "Volume Change From Premarket": _market_open_value(stock, "market_open_validation", "volume_change_from_premarket_volume"),
            "Pre Open Change %": _market_open_value(stock, "market_open_analysis", "pre_open_change_pct"),
            "Open To 09:08 Change %": _market_open_value(stock, "market_open_analysis", "open_to_target_change_pct"),
        })
        rows.append(row)
    return pd.DataFrame(rows)


def generate_scan_report(
    ranked_results,
    all_results=None,
    filtered_results=None,
    top_results=None,
    final_results=None,
    scan_mode=None,
):
    """
    Generate final scanner report.
    """

    try:
        all_rows = all_results if all_results is not None else ranked_results
        filtered_rows = filtered_results if filtered_results is not None else ranked_results
        top_rows = top_results if top_results is not None else ranked_results
        final_rows = final_results if final_results is not None else ranked_results
        scan_type_rows = final_rows or top_rows or filtered_rows or ranked_results or all_rows
        clear_report = build_scan_type_report(scan_type_rows, scan_mode=scan_mode)

        filepath = export_to_excel(
            {
                "All_Stocks_Live_Data": build_report_dataframe(all_rows),
                "Filtered_150": build_report_dataframe(filtered_rows),
                "Top_25": build_report_dataframe(top_rows),
                "Final_Top_10": build_report_dataframe(final_rows),
                "Full_Scan": build_report_dataframe(ranked_results),
                **clear_report,
            }
        )

        logger.info(
            "Final scan report generated"
        )

        return filepath

    except Exception as e:

        logger.error(
            f"Report generation failed: {e}"
        )

        return None
