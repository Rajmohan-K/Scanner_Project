from __future__ import annotations

import asyncio
import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from config import MASTER_ANALYSIS_SETTINGS
from data.market_data import get_live_quote, get_stock_data
from data.market_data_provider import get_market_data_provider
from utils.logger import logger


RANGE_MAP: dict[str, tuple[str, str]] = {
    "1D": ("1d", "5m"),
    "1W": ("5d", "15m"),
    "1M": ("1mo", "1d"),
    "3M": ("3mo", "1d"),
    "6M": ("6mo", "1d"),
    "1Y": ("1y", "1d"),
    "3Y": ("3y", "1wk"),
    "5Y": ("5y", "1wk"),
    "ALL": ("10y", "1mo"),
}

ANALYSIS_VERSION = "v30.1-unified"
SETTINGS_VERSION = hashlib.sha256(
    json.dumps(MASTER_ANALYSIS_SETTINGS, sort_keys=True, default=str).encode("utf-8")
).hexdigest()[:12]

NAME_ALIASES = {
    "MTARTECH": "MTAR Technologies",
    "MTARTECH.NS": "MTAR Technologies",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_stock_symbol(value: Any) -> str:
    raw = str(value or "").strip().upper().replace(" ", "")
    if not raw:
        return ""
    if raw.startswith("^") or "." in raw:
        return raw
    return f"{raw}.NS"


def symbol_base(symbol: str) -> str:
    return normalize_stock_symbol(symbol).split(".")[0].replace("^", "")


def exchange_from_symbol(symbol: str) -> str:
    normalized = normalize_stock_symbol(symbol)
    if normalized.endswith(".NS"):
        return "NSE"
    if normalized.endswith(".BO"):
        return "BSE"
    return normalized.split(".")[-1] if "." in normalized else "NSE"


def humanize_symbol(symbol: str) -> str:
    normalized = normalize_stock_symbol(symbol)
    base = symbol_base(normalized)
    if normalized in NAME_ALIASES or base in NAME_ALIASES:
        return NAME_ALIASES.get(normalized) or NAME_ALIASES.get(base) or base
    return base.replace("-", " ").replace("_", " ").title()


def _number(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
        if math.isfinite(numeric):
            return numeric
    except (TypeError, ValueError):
        pass
    return default


def _round(value: Any, digits: int = 2) -> float:
    return round(_number(value), digits)


def _normalize_df(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    clean = df.copy()
    if isinstance(clean.columns, pd.MultiIndex):
        clean.columns = [
            next((str(part) for part in column if str(part).lower() in {"open", "high", "low", "close", "volume"}), str(column[-1]))
            for column in clean.columns
        ]
    rename = {str(column).lower(): column for column in clean.columns}
    columns = {}
    for name in ("Open", "High", "Low", "Close", "Volume"):
        source = rename.get(name.lower())
        if source is not None:
            columns[source] = name
    clean = clean.rename(columns=columns)
    available = [name for name in ("Open", "High", "Low", "Close", "Volume") if name in clean.columns]
    clean = clean[available].copy()
    for column in available:
        clean[column] = pd.to_numeric(clean[column], errors="coerce")
    return clean.dropna(subset=["Close"]).sort_index()


def candles_from_df(df: pd.DataFrame, limit: int = 1200) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    rows: list[dict[str, Any]] = []
    for index, row in df.tail(limit).iterrows():
        rows.append(
            {
                "time": index.isoformat() if hasattr(index, "isoformat") else str(index),
                "open": _round(row.get("Open")),
                "high": _round(row.get("High")),
                "low": _round(row.get("Low")),
                "close": _round(row.get("Close")),
                "volume": int(_number(row.get("Volume"))),
            }
        )
    return rows


def _ema(series: pd.Series, span: int) -> float:
    if series.empty:
        return 0.0
    return _round(series.ewm(span=span, adjust=False).mean().iloc[-1])


def _rsi(close: pd.Series, period: int = 14) -> float:
    if len(close) < period + 1:
        return 50.0
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, pd.NA)
    value = 100 - (100 / (1 + rs.iloc[-1])) if pd.notna(rs.iloc[-1]) else 50
    return _round(value)


def _macd(close: pd.Series) -> dict[str, float]:
    if close.empty:
        return {"macd": 0, "signal": 0, "histogram": 0}
    fast = close.ewm(span=12, adjust=False).mean()
    slow = close.ewm(span=26, adjust=False).mean()
    line = fast - slow
    signal = line.ewm(span=9, adjust=False).mean()
    hist = line - signal
    return {"macd": _round(line.iloc[-1]), "signal": _round(signal.iloc[-1]), "histogram": _round(hist.iloc[-1])}


def _vwap(df: pd.DataFrame) -> float:
    if df.empty or "Volume" not in df:
        return 0.0
    tail = df.tail(80)
    volume = tail["Volume"].astype(float)
    total_volume = float(volume.sum() or 0)
    if not total_volume:
        return _round(tail["Close"].mean())
    typical = (tail["High"] + tail["Low"] + tail["Close"]) / 3
    return _round((typical * volume).sum() / total_volume)


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    if df.empty or not {"High", "Low", "Close"}.issubset(df.columns):
        return 0.0
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    value = true_range.rolling(period).mean().iloc[-1] if len(true_range) >= period else true_range.mean()
    return _round(value)


def _trend(price: float, ema20: float, ema50: float, ema200: float) -> str:
    if price > ema20 > ema50 and price > ema200:
        return "Bullish"
    if price < ema20 < ema50 or price < ema200:
        return "Bearish"
    return "Sideways"


def _build_trade_plan(
    *,
    horizon: str,
    signal: str,
    price: float,
    entry_trigger: float | None,
    stop_candidate: float | None,
    risk_multipliers: tuple[float, float, float],
    valid_for: str,
    reason: str,
) -> dict[str, Any]:
    if signal == "AVOID" or not entry_trigger or not stop_candidate or stop_candidate >= entry_trigger:
        return {
            "horizon": horizon,
            "signal": signal,
            "valid_for": valid_for,
            "entry_price": None,
            "entry_trigger": None,
            "stop_loss": None,
            "target1": None,
            "target2": None,
            "target3": None,
            "risk_reward_ratio": None,
            "risk_per_share": None,
            "status": "no_trade",
            "reason": reason,
        }

    risk = max(entry_trigger - stop_candidate, price * 0.0025, 0.01)
    target1 = entry_trigger + risk * risk_multipliers[0]
    target2 = entry_trigger + risk * risk_multipliers[1]
    target3 = entry_trigger + risk * risk_multipliers[2]
    return {
        "horizon": horizon,
        "signal": signal,
        "valid_for": valid_for,
        "entry_price": _round(entry_trigger),
        "entry_trigger": _round(entry_trigger),
        "stop_loss": _round(stop_candidate),
        "target1": _round(target1),
        "target2": _round(target2),
        "target3": _round(target3),
        "risk_reward_ratio": _round((target2 - entry_trigger) / risk),
        "risk_per_share": _round(risk),
        "status": "trade_ready" if signal == "BUY" else "watch_for_confirmation",
        "reason": reason,
    }


def _score(value: float, low: float = 0, high: float = 100) -> float:
    return _round(max(low, min(high, value)))


def _score_label(score: float) -> str:
    if score >= 90:
        return "Elite Setup"
    if score >= 80:
        return "Strong Buy"
    if score >= 70:
        return "Buy"
    if score >= 60:
        return "Watchlist"
    if score >= 50:
        return "Neutral"
    return "Avoid"


def _confidence_label(score: float) -> str:
    if score >= 85:
        return "Very High"
    if score >= 70:
        return "High"
    if score >= 55:
        return "Medium"
    return "Low"


def _market_label(score: float) -> str:
    if score >= 80:
        return "Strong Bullish"
    if score >= 65:
        return "Bullish"
    if score >= 45:
        return "Neutral"
    if score >= 30:
        return "Weak"
    return "Bearish"


def _series_return(series: pd.Series, lookback: int) -> float:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if len(clean) < 2:
        return 0.0
    start = clean.iloc[-min(lookback, len(clean))]
    end = clean.iloc[-1]
    return ((end / start) - 1) * 100 if start else 0.0


def _trend_pattern(close: pd.Series, high: pd.Series, low: pd.Series) -> str:
    if len(close) < 12:
        return "Insufficient Data"
    recent_high = high.tail(6).max()
    prior_high = high.tail(18).head(12).max() if len(high) >= 18 else high.head(max(len(high) - 6, 1)).max()
    recent_low = low.tail(6).min()
    prior_low = low.tail(18).head(12).min() if len(low) >= 18 else low.head(max(len(low) - 6, 1)).min()
    recent_return = _series_return(close, 8)
    if recent_high > prior_high and recent_low > prior_low:
        return "Higher High Higher Low"
    if recent_high < prior_high and recent_low < prior_low:
        return "Lower High Lower Low"
    if abs(recent_return) <= 1.5:
        return "Sideways"
    return "Accumulation" if recent_return > 0 else "Distribution"


def _technical_snapshot(label: str, frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty or "Close" not in frame:
        return {"timeframe": label, "trend": "Unavailable", "rsi": None, "macd": {}, "ema_structure": "Unavailable", "volume_strength": "Unavailable", "score": 0}
    close = frame["Close"].astype(float)
    volume = frame["Volume"].astype(float) if "Volume" in frame else close * 0
    ema_fast = _ema(close, min(9, max(2, len(close))))
    ema_slow = _ema(close, min(20, max(3, len(close))))
    rsi = _rsi(close, min(14, max(2, len(close) - 1)))
    macd = _macd(close)
    trend = "Bullish" if close.iloc[-1] > ema_fast >= ema_slow else "Bearish" if close.iloc[-1] < ema_fast <= ema_slow else "Sideways"
    volume_ratio = _number(volume.tail(3).mean()) / _number(volume.tail(20).mean(), 1) if len(volume) >= 5 else 1.0
    score = 45
    score += 20 if trend == "Bullish" else -15 if trend == "Bearish" else 0
    score += 15 if 50 <= rsi <= 70 else -10 if rsi < 42 or rsi > 76 else 0
    score += 10 if macd.get("histogram", 0) > 0 else -5
    score += 10 if volume_ratio >= 1.2 else -5 if volume_ratio < 0.75 else 0
    return {
        "timeframe": label,
        "trend": trend,
        "rsi": rsi,
        "macd": macd,
        "ema_structure": "Bullish Stack" if ema_fast >= ema_slow else "Bearish Stack",
        "volume_strength": "Strong" if volume_ratio >= 1.2 else "Weak" if volume_ratio < 0.75 else "Normal",
        "score": _score(score),
    }


def _timeframe_slices(df: pd.DataFrame, intraday_df: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    frames: list[tuple[str, pd.DataFrame]] = []
    intraday_windows = {"15m": 3, "30m": 6, "1h": 12, "4h": 48}
    for label, window in intraday_windows.items():
        frames.append((label, intraday_df.tail(window) if not intraday_df.empty else pd.DataFrame()))
    frames.append(("1D", df.tail(60)))
    frames.append(("1W", df.tail(260)))
    return frames


def _build_master_analysis(
    *,
    symbol: str,
    price: float,
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    volume: pd.Series,
    df: pd.DataFrame,
    intraday_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    trend: str,
    breakout_status: str,
    intraday_signal: str,
    swing_signal: str,
    intraday_trade_plan: dict[str, Any],
    swing_trade_plan: dict[str, Any],
    ema20: float,
    ema50: float,
    ema200: float,
    rsi: float,
    macd: dict[str, float],
    vwap: float,
    volume_ratio: float,
    risk_reward: float,
    support: float,
    resistance: float,
    atr: float,
) -> dict[str, Any]:
    settings = MASTER_ANALYSIS_SETTINGS
    weights = settings["weights"]
    trend_score = 82 if trend == "Bullish" else 35 if trend == "Bearish" else 55
    trend_pattern = _trend_pattern(close, high, low)
    if trend_pattern == "Higher High Higher Low":
        trend_score += 10
    elif trend_pattern == "Lower High Lower Low":
        trend_score -= 12

    momentum_score = 45
    momentum_score += 20 if price > ema20 else -12
    momentum_score += 14 if macd.get("histogram", 0) > 0 else -8
    momentum_score += 16 if settings["rsi_buy_min"] <= rsi <= settings["rsi_buy_max"] else -12 if rsi > settings["rsi_overheated"] or rsi < 42 else 0
    momentum_score += 8 if price > vwap else -8

    volume_score = 45 + min(volume_ratio, 3) * 18
    if volume_ratio < 0.8:
        volume_score -= 15

    near_resistance_pct = ((resistance - price) / resistance * 100) if resistance else 100
    breakout_probability = 35
    if breakout_status == "Breakout":
        breakout_probability = 86 if volume_ratio >= settings["volume_spike_threshold"] else 72
    elif breakout_status == "About to breakout":
        breakout_probability = 62 if near_resistance_pct <= settings["breakout_near_pct"] else 52
    elif breakout_status == "Rejected":
        breakout_probability = 30
    elif breakout_status == "Weak":
        breakout_probability = 38
    breakout_score = breakout_probability

    stock_return_60 = _series_return(close, 60)
    benchmark_return_60 = _series_return(benchmark_df["Close"], 60) if not benchmark_df.empty and "Close" in benchmark_df else 0
    nifty_outperformance = stock_return_60 - benchmark_return_60
    relative_strength_score = _score(50 + nifty_outperformance * 2.2)

    benchmark_trend = "Unavailable"
    market_strength_score = 50.0
    if not benchmark_df.empty and "Close" in benchmark_df:
        bench_close = benchmark_df["Close"].astype(float)
        bench_ema20 = _ema(bench_close, 20)
        bench_ema50 = _ema(bench_close, 50)
        bench_price = _number(bench_close.iloc[-1])
        benchmark_trend = _trend(bench_price, bench_ema20, bench_ema50, _ema(bench_close, 120))
        market_strength_score = 78 if benchmark_trend == "Bullish" else 35 if benchmark_trend == "Bearish" else 55

    rr_score = _score((risk_reward or 0) / max(settings["min_risk_reward"], 0.1) * 70)
    risk_rating = "Low" if atr / max(price, 1) < 0.018 and price > support else "High" if atr / max(price, 1) > 0.045 or price < ema50 else "Medium"
    risk_penalty = 12 if risk_rating == "High" else 4 if risk_rating == "Medium" else 0

    component_scores = {
        "trend": _score(trend_score),
        "momentum": _score(momentum_score),
        "volume": _score(volume_score),
        "breakout": _score(breakout_score),
        "relative_strength": _score(relative_strength_score),
        "market_alignment": _score(market_strength_score),
        "risk_reward": _score(rr_score),
    }
    total_weight = sum(float(value) for value in weights.values()) or 100
    overall_score = _score(
        sum(component_scores[key] * float(weights.get(key, 0)) for key in component_scores) / total_weight - risk_penalty
    )
    classification = _score_label(overall_score)

    timeframe_rows = [_technical_snapshot(label, frame) for label, frame in _timeframe_slices(df, intraday_df)]
    alignment_score = _score(sum(row.get("score", 0) for row in timeframe_rows) / max(len(timeframe_rows), 1))

    bullish_factors: list[str] = []
    bearish_factors: list[str] = []
    if price > ema20 > ema50:
        bullish_factors.append("Price is above EMA20 and EMA50")
    else:
        bearish_factors.append("EMA structure is not fully aligned")
    if price > ema200:
        bullish_factors.append("Price is above EMA200")
    else:
        bearish_factors.append("Price is below EMA200")
    if volume_ratio >= settings["volume_spike_threshold"]:
        bullish_factors.append(f"Volume spike {volume_ratio:.2f}x average")
    elif volume_ratio < 0.8:
        bearish_factors.append("Volume is below average")
    if relative_strength_score >= 70:
        bullish_factors.append(f"Outperforming Nifty by {nifty_outperformance:.2f}% over recent window")
    elif relative_strength_score < 45:
        bearish_factors.append(f"Underperforming Nifty by {abs(nifty_outperformance):.2f}% over recent window")
    if rsi > settings["rsi_overheated"]:
        bearish_factors.append(f"RSI overheated at {rsi}")
    elif 50 <= rsi <= 70:
        bullish_factors.append(f"RSI healthy at {rsi}")
    if breakout_status in {"Breakout", "About to breakout"}:
        bullish_factors.append(f"Breakout status: {breakout_status}")
    else:
        bearish_factors.append(f"Breakout status: {breakout_status}")
    if risk_rating == "High":
        bearish_factors.append("Risk rating is High due to volatility/support distance")

    if overall_score >= 82 and "BUY" in {intraday_signal, swing_signal}:
        final_action = "BUY NOW"
    elif breakout_status == "About to breakout" and overall_score >= 65:
        final_action = "WAIT FOR BREAKOUT"
    elif trend == "Bullish" and rsi > settings["rsi_overheated"]:
        final_action = "WAIT FOR PULLBACK"
    elif overall_score >= 58:
        final_action = "WATCHLIST"
    else:
        final_action = "AVOID"

    confidence = _score((overall_score * 0.55) + (alignment_score * 0.25) + (component_scores["volume"] * 0.1) + (component_scores["market_alignment"] * 0.1))
    probability = _score(confidence - (10 if risk_rating == "High" else 0) + (6 if breakout_status == "Breakout" else 0))
    preferred_plan = intraday_trade_plan if intraday_trade_plan.get("status") != "no_trade" else swing_trade_plan

    return {
        "symbol": symbol,
        "overall_score": overall_score,
        "classification": classification,
        "confidence_percent": confidence,
        "confidence_label": _confidence_label(confidence),
        "probability_of_success": probability,
        "final_action": final_action,
        "expected_holding_period": preferred_plan.get("valid_for") or "No active trade plan",
        "component_scores": component_scores,
        "market_context": {
            "marketTrend": _market_label(market_strength_score),
            "niftyTrend": benchmark_trend,
            "sectorTrend": "Unavailable",
            "industryStrength": "Unavailable",
            "marketStrengthScore": _round(market_strength_score),
        },
        "relative_strength": {
            "relativeStrengthScore": relative_strength_score,
            "niftyOutperformancePct": _round(nifty_outperformance),
            "commentary": f"Stock return {stock_return_60:.2f}% vs Nifty {benchmark_return_60:.2f}% over recent window.",
        },
        "multi_timeframe": {
            "alignmentScore": alignment_score,
            "timeframes": timeframe_rows,
        },
        "trend_analysis": {
            "pattern": trend_pattern,
            "trendScore": component_scores["trend"],
        },
        "breakout_analysis": {
            "status": "Confirmed" if breakout_status == "Breakout" else "Near Breakout" if breakout_status == "About to breakout" else "Breakdown" if breakout_status == "Rejected" else breakout_status,
            "probabilityPct": _round(breakout_probability),
            "resistance": _round(resistance),
            "distanceToResistancePct": _round(near_resistance_pct),
        },
        "volume_analysis": {
            "volumeStrengthScore": component_scores["volume"],
            "relativeVolume": _round(volume_ratio),
            "obvBias": "Accumulation" if close.tail(5).mean() > close.tail(20).mean() and volume_ratio >= 1 else "Distribution" if price < ema20 else "Neutral",
        },
        "momentum_analysis": {
            "momentumScore": component_scores["momentum"],
            "rsi": rsi,
            "macd": macd,
            "ema20": ema20,
            "ema50": ema50,
            "ema200": ema200,
            "vwap": vwap,
        },
        "risk_analysis": {
            "riskRating": risk_rating,
            "atr": _round(atr),
            "volatilityPct": _round((atr / max(price, 1)) * 100),
            "distanceFromSupportPct": _round(((price - support) / price) * 100 if price else 0),
            "distanceFromResistancePct": _round(((resistance - price) / price) * 100 if price else 0),
        },
        "trade_setups": {
            "intraday": intraday_trade_plan,
            "swing": swing_trade_plan,
            "positional": {
                **swing_trade_plan,
                "horizon": "positional",
                "valid_for": "Multi-week setup; confirm with weekly trend before entry",
                "signal": "WATCH" if overall_score >= 65 and trend != "Bearish" else "AVOID",
            },
        },
        "ai_explanation": {
            "summary": f"{classification}: {final_action} with {confidence}% confidence. Prefer no trade if confirmation is missing.",
            "bullishFactors": bullish_factors,
            "bearishFactors": bearish_factors,
            "tradeRisks": bearish_factors[:4] or ["No major risk flag from configured checks."],
            "suggestedAction": final_action,
            "probabilityOfSuccess": probability,
            "confidence": confidence,
            "expectedHoldingPeriod": preferred_plan.get("valid_for") or "No active trade plan",
        },
    }


def build_rule_analysis(
    symbol: str,
    quote: dict[str, Any],
    historical: pd.DataFrame,
    intraday: pd.DataFrame,
    benchmark: pd.DataFrame | None = None,
) -> dict[str, Any]:
    df = historical if not historical.empty else intraday
    if df.empty:
        return {"status": "unavailable", "symbol": symbol, "message": "No candle data available for analysis."}

    close = df["Close"].astype(float)
    high = df["High"].astype(float) if "High" in df else close
    low = df["Low"].astype(float) if "Low" in df else close
    volume = df["Volume"].astype(float) if "Volume" in df else close * 0
    intraday_df = intraday if not intraday.empty else df.tail(80)
    price = _number(quote.get("current_price") or close.iloc[-1])
    previous_close = _number(quote.get("previous_close") or (close.iloc[-2] if len(close) > 1 else close.iloc[-1]))
    open_price = _number(quote.get("open") or (df["Open"].iloc[-1] if "Open" in df else close.iloc[-1]))
    change = price - previous_close if previous_close else 0.0
    change_pct = (change / previous_close * 100) if previous_close else 0.0
    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)
    ema200 = _ema(close, 200)
    rsi = _rsi(close)
    macd = _macd(close)
    vwap = _vwap(intraday_df)
    avg_volume = _number(volume.tail(20).mean())
    latest_volume = _number(volume.iloc[-1])
    volume_ratio = latest_volume / avg_volume if avg_volume else 1.0
    support_levels = sorted({_round(low.tail(window).min()) for window in (20, 50, min(len(low), 100)) if len(low) >= window})
    resistance_levels = sorted({_round(high.tail(window).max()) for window in (20, 50, min(len(high), 100)) if len(high) >= window})
    support = support_levels[-1] if support_levels else _round(low.tail(20).min())
    resistance = resistance_levels[-1] if resistance_levels else _round(high.tail(20).max())
    near_resistance_pct = ((resistance - price) / resistance * 100) if resistance else 100
    closes_above_resistance = bool(price > resistance and close.iloc[-1] >= resistance)
    volume_increasing = bool(len(volume) >= 5 and volume.tail(5).mean() > volume.tail(20).mean())
    breakout_status = "Breakout" if closes_above_resistance and volume_ratio >= 1.25 else "About to breakout" if 0 <= near_resistance_pct <= 2 and volume_increasing else "Rejected" if price < ema20 and near_resistance_pct < 3 else "Weak"
    trend = _trend(price, ema20, ema50, ema200)
    gap_pct = ((open_price - previous_close) / previous_close * 100) if previous_close else 0
    gap_status = "Gap Up" if gap_pct >= 0.75 else "Gap Down" if gap_pct <= -0.75 else "Flat Open"

    intraday_atr = _atr(intraday_df) or max(price * 0.006, 0.05)
    swing_atr = _atr(df) or max(price * 0.025, 0.05)
    intraday_low = intraday_df["Low"].astype(float) if not intraday_df.empty and "Low" in intraday_df else low
    intraday_high = intraday_df["High"].astype(float) if not intraday_df.empty and "High" in intraday_df else high
    intraday_support = _round(intraday_low.tail(min(len(intraday_low), 48)).min()) if len(intraday_low) else support
    intraday_resistance = _round(intraday_high.tail(min(len(intraday_high), 48)).max()) if len(intraday_high) else resistance

    intraday_buy = price > vwap and price > ema20 and 50 <= rsi <= 70 and volume_ratio > 1 and trend != "Bearish"
    swing_buy = price > ema50 and price > ema200 and 45 <= rsi <= 72 and breakout_status in {"Breakout", "About to breakout"}
    avoid = price < vwap or price < ema20 or price < ema50 or rsi < 42 or volume_ratio < 0.8 or trend == "Bearish"
    watch = breakout_status == "About to breakout" and not avoid
    intraday_signal = "BUY" if intraday_buy else "WATCH" if watch else "AVOID"
    swing_signal = "BUY" if swing_buy else "WATCH" if watch or (price > ema50 and trend != "Bearish") else "AVOID"
    intraday_entry = price if intraday_signal == "BUY" else max(price, vwap, ema20, intraday_resistance * 1.001) if intraday_signal == "WATCH" else None
    intraday_stop = None
    if intraday_entry:
        stop_buffer = max(intraday_atr * 0.65, intraday_entry * 0.004)
        intraday_candidates = [intraday_entry - stop_buffer, vwap - stop_buffer, intraday_support]
        intraday_stop = max((level for level in intraday_candidates if 0 < level < intraday_entry), default=intraday_entry - stop_buffer)
    swing_entry = price if swing_signal == "BUY" else max(price, resistance * 1.002, ema50) if swing_signal == "WATCH" else None
    swing_stop = None
    if swing_entry:
        swing_buffer_stop = swing_entry - max(swing_atr * 1.15, swing_entry * 0.018)
        swing_candidates = [support, ema50 - swing_atr * 0.35, swing_buffer_stop]
        swing_stop = max((level for level in swing_candidates if 0 < level < swing_entry), default=swing_buffer_stop)
    volume_text = "Strong volume" if volume_ratio >= 1.25 else "Average volume" if volume_ratio >= 0.8 else "Weak/falling volume"
    delivery_strength = "Unavailable"
    intraday_reason = (
        f"{intraday_signal}: price is {'above' if price > vwap else 'below'} VWAP {vwap}, "
        f"{'above' if price > ema20 else 'below'} EMA20 {ema20}, RSI {rsi}, "
        f"relative volume {volume_ratio:.2f}x, intraday resistance {intraday_resistance}."
    )
    swing_reason = (
        f"{swing_signal}: price is {'above' if price > ema50 else 'below'} EMA50 {ema50} and "
        f"{'above' if price > ema200 else 'below'} EMA200 {ema200}; trend {trend}, "
        f"breakout status {breakout_status}, support {support}, resistance {resistance}."
    )
    intraday_trade_plan = _build_trade_plan(
        horizon="intraday",
        signal=intraday_signal,
        price=price,
        entry_trigger=intraday_entry,
        stop_candidate=intraday_stop,
        risk_multipliers=(1.0, 1.5, 2.0),
        valid_for="Same trading day only",
        reason=intraday_reason,
    )
    swing_trade_plan = _build_trade_plan(
        horizon="swing",
        signal=swing_signal,
        price=price,
        entry_trigger=swing_entry,
        stop_candidate=swing_stop,
        risk_multipliers=(1.5, 2.5, 3.5),
        valid_for="Multi-day setup, usually 3-30 trading days",
        reason=swing_reason,
    )
    active_trade_plan = (
        intraday_trade_plan
        if intraday_trade_plan.get("status") != "no_trade"
        else swing_trade_plan
        if swing_trade_plan.get("status") != "no_trade"
        else intraday_trade_plan
    )
    reason_parts = [
        intraday_reason,
        swing_reason,
        f"Trend is {trend}, RSI {rsi}, volume {volume_ratio:.2f}x average.",
        f"Breakout status is {breakout_status} near resistance {resistance}.",
    ]
    benchmark_df = benchmark if benchmark is not None else pd.DataFrame()
    master_analysis = _build_master_analysis(
        symbol=symbol,
        price=price,
        close=close,
        high=high,
        low=low,
        volume=volume,
        df=df,
        intraday_df=intraday_df,
        benchmark_df=benchmark_df,
        trend=trend,
        breakout_status=breakout_status,
        intraday_signal=intraday_signal,
        swing_signal=swing_signal,
        intraday_trade_plan=intraday_trade_plan,
        swing_trade_plan=swing_trade_plan,
        ema20=ema20,
        ema50=ema50,
        ema200=ema200,
        rsi=rsi,
        macd=macd,
        vwap=vwap,
        volume_ratio=volume_ratio,
        risk_reward=active_trade_plan.get("risk_reward_ratio") or 0,
        support=support,
        resistance=resistance,
        atr=swing_atr,
    )

    return {
        "status": "ok",
        "symbol": symbol,
        "generated_at": _now(),
        "stale": bool(quote.get("stale")),
        "intraday_view": intraday_signal,
        "swing_view": swing_signal,
        "breakout_status": breakout_status,
        "trend": trend,
        "support_levels": support_levels[-3:],
        "resistance_levels": resistance_levels[-3:],
        "intraday_trade_plan": intraday_trade_plan,
        "swing_trade_plan": swing_trade_plan,
        "entry_price": active_trade_plan.get("entry_price"),
        "stop_loss": active_trade_plan.get("stop_loss"),
        "target1": active_trade_plan.get("target1"),
        "target2": active_trade_plan.get("target2"),
        "target3": active_trade_plan.get("target3"),
        "risk_reward_ratio": active_trade_plan.get("risk_reward_ratio"),
        "volume_analysis": {"label": volume_text, "latest_volume": int(latest_volume), "avg_volume": int(avg_volume), "relative_volume": _round(volume_ratio)},
        "indicators": {"rsi": rsi, "macd": macd, "ema20": ema20, "ema50": ema50, "ema200": ema200, "vwap": vwap},
        "gap_status": {"label": gap_status, "gap_pct": _round(gap_pct)},
        "delivery_strength": delivery_strength,
        "master_analysis": master_analysis,
        "reason": " ".join(reason_parts),
        "quote": {
            **quote,
            "current_price": _round(price),
            "previous_close": _round(previous_close),
            "change": _round(change),
            "change_pct": _round(change_pct),
        },
    }


@dataclass
class CachedValue:
    data: Any
    updated_at: float
    stale: bool = False
    error: str = ""


@dataclass
class CentralStockDataService:
    base_dir: Path
    quote_ttl: float = 5.0
    candle_ttl: float = 60.0
    analysis_ttl: float = 10.0
    background_interval: float = 5.0
    tracked_symbols: set[str] = field(default_factory=set)
    quote_cache: dict[str, CachedValue] = field(default_factory=dict)
    candle_cache: dict[tuple[str, str], CachedValue] = field(default_factory=dict)
    analysis_cache: dict[str, CachedValue] = field(default_factory=dict)
    unavailable_cache: dict[str, CachedValue] = field(default_factory=dict)
    _task: asyncio.Task | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @staticmethod
    def _recommendation(value: Any) -> str:
        upper = str(value or "AVOID").upper()
        return "BUY" if "BUY" in upper else "WATCH" if "WATCH" in upper or "WAIT" in upper else "AVOID"

    def _horizon_contract(self, signal: Any, plan: dict[str, Any], master: dict[str, Any], score_name: str) -> dict[str, Any]:
        stop_loss = plan.get("stop_loss")
        return {
            "recommendation": self._recommendation(signal),
            "score": (master.get("component_scores") or {}).get(score_name),
            "confidence": master.get("confidence_percent"),
            "entry": plan.get("entry_price"),
            "stopLoss": stop_loss,
            "targets": [value for value in (plan.get("target1"), plan.get("target2"), plan.get("target3")) if value is not None],
            "reasons": [plan.get("reason")] if plan.get("reason") else [],
            "invalidation": plan.get("invalidation") or (f"Exit below {stop_loss}" if stop_loss else "No active trade; wait for confirmation"),
            "tradePlan": plan,
        }

    def _analysis_response(self, payload: dict[str, Any], cached_at: float, cache_hit: bool) -> dict[str, Any]:
        age = max(0.0, datetime.now().timestamp() - cached_at)
        master = payload.get("master_analysis") or {}
        breakout = master.get("breakout_analysis") or {}
        breakout_status = str(payload.get("breakout_status") or "Unavailable")
        result = dict(payload)
        result.update({
            "masterRecommendation": self._recommendation(master.get("final_action")),
            "overallScore": master.get("overall_score"),
            "confidence": master.get("confidence_percent"),
            "risk": (master.get("risk_analysis") or {}).get("riskRating"),
            "intraday": self._horizon_contract(payload.get("intraday_view"), payload.get("intraday_trade_plan") or {}, master, "momentum"),
            "swing": self._horizon_contract(payload.get("swing_view"), payload.get("swing_trade_plan") or {}, master, "trend"),
            "breakout": {"status": breakout_status, "breakoutLevel": breakout.get("resistance"), "distanceToBreakoutPercent": breakout.get("distanceToResistancePct"), "probability": breakout.get("probabilityPct"), "reasons": [f"{breakout_status} based on resistance and volume confirmation"]},
            "bullishReasons": (master.get("ai_explanation") or {}).get("bullishFactors") or [],
            "bearishReasons": (master.get("ai_explanation") or {}).get("bearishFactors") or [],
            "finalExplanation": (master.get("ai_explanation") or {}).get("summary") or payload.get("reason"),
            "lastUpdated": payload.get("generated_at") or _now(),
            "dataAgeSeconds": round(age, 2),
            "isStale": bool(payload.get("stale") or age > self.analysis_ttl * 2),
            "dataSource": ((payload.get("stock") or {}).get("source") or "central-stock-data-service"),
            "analysisVersion": ANALYSIS_VERSION,
            "settingsVersion": SETTINGS_VERSION,
            "cache": {"hit": cache_hit, "calculatedAt": payload.get("generated_at"), "ageSeconds": round(age, 2)},
        })
        return result

    def __post_init__(self) -> None:
        self.provider = get_market_data_provider()
        self.symbol_records = self._load_symbol_records()

    def _load_symbol_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        seen: set[str] = set()
        for path in (self.base_dir / "all_symbols.txt", self.base_dir / "ui" / "all_symbols.txt"):
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                symbol = normalize_stock_symbol(line)
                if not symbol or symbol in seen:
                    continue
                seen.add(symbol)
                records.append({"symbol": symbol, "exchange": exchange_from_symbol(symbol), "name": humanize_symbol(symbol)})
        return records

    def search(self, query: str, limit: int = 12) -> dict[str, Any]:
        needle = str(query or "").strip().upper()
        if not needle:
            return {"status": "ok", "query": query, "results": []}
        scored_matches: list[tuple[int, dict[str, Any]]] = []
        for record in self.symbol_records:
            base = symbol_base(record["symbol"]).upper()
            name = str(record.get("name") or "").upper()
            haystack = f"{record['symbol']} {name}".upper()
            if base == needle:
                scored_matches.append((0, record))
            elif base.startswith(needle):
                scored_matches.append((1, record))
            elif name.startswith(needle):
                scored_matches.append((2, record))
            elif needle in haystack:
                scored_matches.append((3, record))
        matches = [record for _, record in sorted(scored_matches, key=lambda item: (item[0], item[1]["symbol"]))[:limit]]
        normalized = normalize_stock_symbol(needle)
        exact_alias = normalized in NAME_ALIASES or symbol_base(normalized) in NAME_ALIASES
        allow_synthetic = exact_alias or (not matches and len(symbol_base(normalized)) >= 4)
        if normalized and allow_synthetic and not any(row["symbol"] == normalized for row in matches):
            matches.insert(0, {"symbol": normalized, "exchange": exchange_from_symbol(normalized), "name": humanize_symbol(normalized)})
        return {"status": "ok", "query": query, "results": matches[:limit]}

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    async def _worker(self) -> None:
        while True:
            symbols = list(self.tracked_symbols)[:120]
            for symbol in symbols:
                try:
                    await self.get_stock(symbol, allow_stale=True)
                    await self.get_analysis(symbol, allow_stale=True)
                except Exception as exc:
                    logger.debug(f"Background stock refresh failed for {symbol}: {exc}")
            await asyncio.sleep(self.background_interval)

    async def _fetch_quote(self, symbol: str) -> dict[str, Any]:
        quote = await asyncio.to_thread(get_live_quote, symbol, False)
        if not quote:
            quote = await asyncio.to_thread(self.provider.get_quote, symbol, False)
        return quote or {}

    async def get_stock(self, symbol: str, allow_stale: bool = True) -> dict[str, Any]:
        normalized = normalize_stock_symbol(symbol)
        if not normalized:
            return {"status": "error", "message": "valid symbol required"}
        cached = self.quote_cache.get(normalized)
        now_ts = datetime.now().timestamp()
        unavailable = self.unavailable_cache.get(normalized)
        if unavailable and now_ts - unavailable.updated_at < 300:
            return {**unavailable.data, "stale": True}
        if cached and now_ts - cached.updated_at < self.quote_ttl:
            self.tracked_symbols.add(normalized)
            return cached.data
        try:
            quote = await asyncio.wait_for(self._fetch_quote(normalized), timeout=8)
            candles_payload = await self.get_candles(normalized, "1D", allow_stale=True)
            candles = candles_payload.get("candles") or []
            if not quote and not candles:
                raise RuntimeError("No market data returned by provider")
            last_close = quote.get("current_price") or (candles[-1]["close"] if candles else None)
            previous = quote.get("previous_close") or (candles[-2]["close"] if len(candles) > 1 else last_close)
            change = _number(last_close) - _number(previous)
            change_pct = change / _number(previous, 1) * 100 if previous else 0
            data = {
                "status": "ok",
                "symbol": normalized,
                "exchange": exchange_from_symbol(normalized),
                "name": quote.get("short_name") or quote.get("name") or humanize_symbol(normalized),
                "logo": "",
                "quote": {**quote, "current_price": _round(last_close), "change": _round(change), "change_pct": _round(change_pct), "updated_at": _now()},
                "stale": False,
                "updated_at": _now(),
                "source": quote.get("source") or quote.get("provider") or "yfinance",
            }
            self.quote_cache[normalized] = CachedValue(data, now_ts)
            self.unavailable_cache.pop(normalized, None)
            self.tracked_symbols.add(normalized)
            return data
        except Exception as exc:
            if cached and allow_stale:
                stale = {**cached.data, "stale": True, "error": str(exc)}
                self.quote_cache[normalized] = CachedValue(stale, cached.updated_at, stale=True, error=str(exc))
                return stale
            error = {
                "status": "error",
                "symbol": normalized,
                "stale": True,
                "message": f"Stock data unavailable for {normalized}. Symbol may be invalid, newly listed, or unavailable from the configured data provider.",
                "provider_error": str(exc),
                "updated_at": _now(),
            }
            self.unavailable_cache[normalized] = CachedValue(error, now_ts, stale=True, error=str(exc))
            self.tracked_symbols.discard(normalized)
            return error

    async def get_candles(self, symbol: str, range_key: str = "1D", allow_stale: bool = True) -> dict[str, Any]:
        normalized = normalize_stock_symbol(symbol)
        range_name = str(range_key or "1D").upper()
        period, interval = RANGE_MAP.get(range_name, RANGE_MAP["1D"])
        key = (normalized, range_name)
        cached = self.candle_cache.get(key)
        now_ts = datetime.now().timestamp()
        if cached and now_ts - cached.updated_at < self.candle_ttl:
            return cached.data
        try:
            raw = await asyncio.wait_for(asyncio.to_thread(get_stock_data, normalized, period, interval), timeout=12)
            df = _normalize_df(raw)
            if df.empty:
                raise RuntimeError("No candle data returned")
            data = {
                "status": "ok",
                "symbol": normalized,
                "range": range_name,
                "period": period,
                "interval": interval,
                "candles": candles_from_df(df),
                "stale": False,
                "updated_at": _now(),
            }
            self.candle_cache[key] = CachedValue(data, now_ts)
            return data
        except Exception as exc:
            if cached and allow_stale:
                stale = {**cached.data, "stale": True, "error": str(exc)}
                self.candle_cache[key] = CachedValue(stale, cached.updated_at, stale=True, error=str(exc))
                return stale
            return {"status": "error", "symbol": normalized, "range": range_name, "candles": [], "stale": True, "message": str(exc), "updated_at": _now()}

    async def get_analysis(self, symbol: str, allow_stale: bool = True) -> dict[str, Any]:
        normalized = normalize_stock_symbol(symbol)
        cached = self.analysis_cache.get(normalized)
        now_ts = datetime.now().timestamp()
        unavailable = self.unavailable_cache.get(normalized)
        if unavailable and now_ts - unavailable.updated_at < 300 and not cached:
            return {
                "status": "error",
                "symbol": normalized,
                "message": unavailable.data.get("message") or "Stock data unavailable",
                "stale": True,
                "generated_at": _now(),
            }
        if cached and now_ts - cached.updated_at < self.analysis_ttl:
            return self._analysis_response(cached.data, cached.updated_at, True)
        try:
            stock = await self.get_stock(normalized, allow_stale=True)
            if stock.get("status") == "error" and not stock.get("quote"):
                raise RuntimeError(stock.get("message") or f"Stock data unavailable for {normalized}")
            quote = stock.get("quote") or {}
            historical_payload = {}
            for range_key in ("1Y", "6M", "3M", "1M", "1W", "1D"):
                historical_payload = await self.get_candles(normalized, range_key, allow_stale=True)
                if historical_payload.get("candles"):
                    break
            intraday_payload = {}
            for range_key in ("1D", "1W"):
                intraday_payload = await self.get_candles(normalized, range_key, allow_stale=True)
                if intraday_payload.get("candles"):
                    break
            if not (historical_payload.get("candles") or intraday_payload.get("candles")):
                raise RuntimeError(f"No candle data available for {normalized}")
            benchmark_payload = await self.get_candles("^NSEI", "6M", allow_stale=True)
            historical = pd.DataFrame(historical_payload.get("candles") or [])
            intraday = pd.DataFrame(intraday_payload.get("candles") or [])
            benchmark = pd.DataFrame(benchmark_payload.get("candles") or [])
            for df in (historical, intraday, benchmark):
                if not df.empty:
                    df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}, inplace=True)
            data = build_rule_analysis(normalized, quote, historical, intraday, benchmark)
            data["stock"] = stock
            data["stale"] = bool(stock.get("stale") or historical_payload.get("stale") or intraday_payload.get("stale") or benchmark_payload.get("stale"))
            self.analysis_cache[normalized] = CachedValue(data, now_ts)
            return self._analysis_response(data, now_ts, False)
        except Exception as exc:
            if cached and allow_stale:
                stale = {**cached.data, "stale": True, "error": str(exc)}
                self.analysis_cache[normalized] = CachedValue(stale, cached.updated_at, stale=True, error=str(exc))
                return self._analysis_response(stale, cached.updated_at, True)
            message = str(exc)
            error = {
                "status": "error",
                "symbol": normalized,
                "message": message,
                "stale": True,
                "generated_at": _now(),
            }
            self.unavailable_cache[normalized] = CachedValue(error, now_ts, stale=True, error=message)
            self.tracked_symbols.discard(normalized)
            return error


stock_data_service = CentralStockDataService(Path(__file__).resolve().parent.parent)


async def encode_sse(event: str, payload: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n".encode("utf-8")
