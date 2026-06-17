from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from utils.helpers import calculate_pct_change, normalize_value


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _normalize_ratio(value: float) -> float:
    if value is None or not isinstance(value, (int, float)):
        return 0.0
    return max(min(value, 1.0), -1.0)


def _extract_opening_frame(df: pd.DataFrame, open_time: str = "09:08") -> pd.DataFrame:
    if df is None or df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return pd.DataFrame()

    try:
        target_time = datetime.strptime(open_time, "%H:%M").time()
    except ValueError:
        return pd.DataFrame()

    if df.index.tz is not None:
        df = df.tz_convert(None)

    latest_date = df.index[-1].date()
    same_day = df.loc[df.index.date == latest_date]
    if same_day.empty:
        same_day = df

    opening_entries = same_day.loc[same_day.index.time >= target_time].head(8)
    return opening_entries


def _build_price_acceptance(current_price: float, key_levels: dict[str, float]) -> dict[str, float]:
    valid_levels = [
        float(value)
        for value in (key_levels or {}).values()
        if isinstance(value, (int, float)) and value > 0
    ]
    if not valid_levels:
        return {
            "price_acceptance_above_key_levels": 0.0,
            "price_rejection_below_key_levels": 0.0,
        }

    accepted = sum(1 for level in valid_levels if current_price >= level)
    rejected = sum(1 for level in valid_levels if current_price < level)
    total = len(valid_levels)
    return {
        "price_acceptance_above_key_levels": round((accepted / total) * 100, 2),
        "price_rejection_below_key_levels": round((rejected / total) * 100, 2),
    }


def _build_order_flow(opening_df: pd.DataFrame) -> dict[str, float]:
    if opening_df is None or opening_df.empty:
        return {
            "order_flow_strength": 0.0,
            "buy_sell_pressure": 0.0,
            "opening_range_strength": 0.0,
        }

    opening_df = opening_df.copy()
    opening_df["movement"] = opening_df["Close"] - opening_df["Open"]
    weighted_flow = (opening_df["movement"] * opening_df["Volume"]).sum()
    total_volume = opening_df["Volume"].sum() or 1.0
    order_flow_strength = round(weighted_flow / total_volume, 4) * 100

    up_bars = float((opening_df["movement"] > 0).sum())
    down_bars = float((opening_df["movement"] < 0).sum())
    buy_sell_pressure = round(_normalize_ratio((up_bars - down_bars) / max(len(opening_df), 1)) * 100, 2)

    open_price = float(opening_df["Open"].iloc[0])
    high_price = float(opening_df["High"].max())
    low_price = float(opening_df["Low"].min())
    opening_range_strength = 0.0
    if high_price != low_price and open_price:
        opening_range_strength = round((high_price - low_price) / open_price * 100, 2)

    return {
        "order_flow_strength": round(order_flow_strength, 2),
        "buy_sell_pressure": buy_sell_pressure,
        "opening_range_strength": opening_range_strength,
    }


def _calculate_volume_signals(
    intraday_df: pd.DataFrame | None,
    premarket_volume: float,
    current_volume: float,
) -> dict[str, float]:
    if intraday_df is None or intraday_df.empty:
        return {
            "volume_change_from_premarket_volume": 0.0,
            "relative_volume_increase": 0.0,
        }

    avg_volume = float(intraday_df["Volume"].tail(20).mean()) if len(intraday_df) >= 20 else float(intraday_df["Volume"].mean())
    if avg_volume <= 0:
        avg_volume = 1.0

    relative_volume_increase = round((current_volume / avg_volume) * 100, 2) if current_volume else 0.0
    volume_change_from_premarket = round(calculate_pct_change(premarket_volume or avg_volume, current_volume or avg_volume), 2)
    return {
        "volume_change_from_premarket_volume": volume_change_from_premarket,
        "relative_volume_increase": relative_volume_increase,
    }


def build_market_open_validation(
    symbol: str,
    quote_data: dict[str, Any],
    intraday_df: pd.DataFrame | None = None,
    open_time: str = "09:08",
    key_levels: dict[str, float] | None = None,
    premarket_price: float | None = None,
    premarket_volume: float | None = None,
) -> dict[str, Any]:
    previous_close = _safe_float(quote_data.get("previous_close"))
    opening_price = _safe_float(quote_data.get("open"))
    current_price = _safe_float(quote_data.get("current_price") or quote_data.get("last_price") or opening_price)
    current_volume = _safe_float(quote_data.get("current_volume") or quote_data.get("volume") or 0)
    premarket_price = _safe_float(premarket_price or quote_data.get("premarket_price") or previous_close)
    premarket_volume = _safe_float(premarket_volume or quote_data.get("premarket_volume") or 0)

    opening_df = _extract_opening_frame(intraday_df, open_time=open_time)
    order_flow = _build_order_flow(opening_df)
    volume_signals = _calculate_volume_signals(opening_df if not opening_df.empty else intraday_df, premarket_volume, current_volume)
    acceptance = _build_price_acceptance(current_price, key_levels or {})

    gap_up_pct = round(calculate_pct_change(previous_close, opening_price), 2) if opening_price and previous_close else 0.0
    gap_down_pct = round(-gap_up_pct if gap_up_pct < 0 else 0.0, 2)
    opening_strength_pct = round(calculate_pct_change(opening_price, current_price), 2) if opening_price else 0.0
    opening_weakness_pct = round(-opening_strength_pct if opening_strength_pct < 0 else 0.0, 2)
    price_change_from_premarket_analysis = round(calculate_pct_change(premarket_price, current_price), 2) if premarket_price else 0.0

    strength_signals = [
        min(max(gap_up_pct, 0), 5),
        min(max(opening_strength_pct, 0), 5),
        min(max(order_flow.get("order_flow_strength", 0), -10), 10),
        min(max(volume_signals.get("relative_volume_increase", 0) / 10, 0), 10),
        min(max(acceptance.get("price_acceptance_above_key_levels", 0) / 10, 0), 10),
    ]
    weakness_signals = [
        min(max(gap_down_pct, 0), 5),
        min(max(opening_weakness_pct, 0), 5),
        min(max(-order_flow.get("order_flow_strength", 0), 0), 10),
        min(max(volume_signals.get("relative_volume_increase", 0) / 10, 0), 10),
        min(max(acceptance.get("price_rejection_below_key_levels", 0) / 10, 0), 10),
    ]

    premarket_confidence_score = round(max(0.0, min(100.0, 50 + sum(strength_signals) - sum(weakness_signals))), 2)

    confirmation_score = 0.0
    if opening_price and current_price:
        confirmation_score += abs(opening_strength_pct) * 4.0
    confirmation_score += order_flow.get("order_flow_strength", 0) * 0.7
    confirmation_score += volume_signals.get("relative_volume_increase", 0) * 0.25
    confirmation_score += acceptance.get("price_acceptance_above_key_levels", 0) * 0.10
    confirmation_score = round(max(0.0, min(100.0, confirmation_score / 2.0)), 2)

    quality_score = round(
        normalize_value(premarket_confidence_score, 0, 100) * 0.3 +
        normalize_value(confirmation_score, 0, 100) * 0.4 +
        normalize_value(opening_strength_pct, -5, 10) * 0.2 +
        normalize_value(order_flow.get("order_flow_strength", 0), -20, 20) * 0.1,
        2,
    )

    if quality_score >= 90:
        classification = "Exceptional Opportunity"
    elif quality_score >= 80:
        classification = "High Probability"
    elif quality_score >= 70:
        classification = "Good Opportunity"
    elif quality_score >= 60:
        classification = "Watchlist"
    else:
        classification = "Ignore"

    candidates = {
        "confirmed_bullish_candidate": opening_strength_pct > 0 and acceptance.get("price_acceptance_above_key_levels", 0) >= 50 and quality_score >= 70,
        "confirmed_bearish_candidate": opening_weakness_pct > 0 and acceptance.get("price_rejection_below_key_levels", 0) >= 50 and quality_score >= 70,
        "failed_premarket_candidate": quality_score < 60 and gap_up_pct > 1 and opening_weakness_pct > 1,
        "strong_gap_continuation_stock": gap_up_pct >= 1.0 and opening_strength_pct >= 0.5,
        "gap_fill_candidate": gap_down_pct >= 1.0 and current_price <= previous_close,
    }

    return {
        "symbol": symbol,
        "premarket_price": round(premarket_price, 2),
        "opening_price": round(opening_price, 2),
        "current_price": round(current_price, 2),
        "premarket_change_pct": round(calculate_pct_change(previous_close, premarket_price), 2) if previous_close and premarket_price else 0.0,
        "open_change_pct": round(calculate_pct_change(previous_close, opening_price), 2) if previous_close and opening_price else 0.0,
        "current_change_pct": round(calculate_pct_change(previous_close, current_price), 2) if previous_close and current_price else 0.0,
        "volume_change_pct": volume_signals.get("volume_change_from_premarket_volume", 0.0),
        "score_improvement_pct": round(max(0.0, quality_score - premarket_confidence_score), 2),
        "score_degradation_pct": round(max(0.0, premarket_confidence_score - quality_score), 2),
        "gap_up_pct": gap_up_pct,
        "gap_down_pct": gap_down_pct,
        "opening_strength_pct": opening_strength_pct,
        "opening_weakness_pct": opening_weakness_pct,
        "price_change_from_premarket_analysis": price_change_from_premarket_analysis,
        "volume_change_from_premarket_volume": volume_signals.get("volume_change_from_premarket_volume", 0.0),
        "relative_volume_increase": volume_signals.get("relative_volume_increase", 0.0),
        **order_flow,
        **acceptance,
        "premarket_confidence_score": premarket_confidence_score,
        "market_open_confirmation_score": confirmation_score,
        "final_trade_quality_score": quality_score,
        "opportunity_classification": classification,
        "candidate_flags": candidates,
    }
