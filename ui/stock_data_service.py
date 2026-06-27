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
    if raw.startswith("^"):
        return raw
    # Synthetic ISINs are placeholder values — not valid tradeable symbols
    if raw.startswith("SYN_"):
        return ""
    
    if raw.endswith(".NS") or raw.endswith(".BO"):
        return raw[:-3]
    if "." in raw:
        return raw.split(".")[0]
    return raw


def symbol_base(symbol: str) -> str:
    return normalize_stock_symbol(symbol).split(".")[0].replace("^", "")


def exchange_from_symbol(symbol: str) -> str:
    s = str(symbol).strip().upper()
    if s.endswith(".NS"):
        return "NSE"
    if s.endswith(".BO"):
        return "BSE"
    return s.split(".")[-1] if "." in s else "NSE"


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
    ema9 = _ema(close, 9)
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
    gap_pct = ((open_price - previous_close) / previous_close * 100) if previous_close else 0
    gap_status = "Gap Up" if gap_pct >= 0.75 else "Gap Down" if gap_pct <= -0.75 else "Flat Open"
    trend = _trend(price, ema20, ema50, ema200)

    # Determine direction
    direction = "BUY" if price >= vwap else "SELL"

    # --- Advanced Profitability Calculations ---
    current_price = _round(price)
    breakout_level = _round(resistance if resistance > 0 else (high.tail(20).max() if not high.empty else current_price))
    breakdown_level = _round(support if support > 0 else (low.tail(20).min() if not low.empty else current_price))
    
    # Intraday High / Low
    intraday_high = _round(quote.get("day_high") or (intraday_df["High"].max() if not intraday_df.empty and "High" in intraday_df else (high.max() if not high.empty else current_price)))
    if intraday_high < current_price:
        intraday_high = current_price
    
    intraday_low = _round(quote.get("day_low") or (intraday_df["Low"].min() if not intraday_df.empty and "Low" in intraday_df else (low.min() if not low.empty else current_price)))
    if intraday_low > current_price:
        intraday_low = current_price

    distance_from_intraday_high_percent = _round(((intraday_high - current_price) / intraday_high) * 100) if intraday_high > 0 else 0.0
    distance_from_intraday_low_percent = _round(((current_price - intraday_low) / current_price) * 100) if current_price > 0 else 0.0
    
    distance_from_vwap_percent = _round((abs(current_price - vwap) / vwap) * 100) if vwap > 0 else 0.0
    volume_vs_avg = _round(volume_ratio)
    already_moved_percent = _round(change_pct)

    if direction == "BUY":
        # Calculate entry price
        entry_price = current_price if current_price >= breakout_level else breakout_level
        # Stop Loss strictly within 1.0% to 1.5%, say 1.2%
        stop_loss = _round(entry_price * 0.988)
        # Targets based on realistic 1.5% profit potential
        target_1 = _round(entry_price * 1.015)
        target_2 = _round(entry_price * 1.030)
        
        expected_profit_percent = _round(((target_1 - current_price) / current_price) * 100) if current_price > 0 else 0.0
        expected_loss_percent = _round(((current_price - stop_loss) / current_price) * 100) if current_price > 0 else 0.0
        risk_reward_ratio = _round(expected_profit_percent / expected_loss_percent) if expected_loss_percent > 0 else 0.0
        distance_to_breakout_percent = _round(((breakout_level - current_price) / current_price) * 100) if breakout_level > current_price else 0.0
        remaining_upside_percent = expected_profit_percent

        # Breakout status
        if current_price >= breakout_level:
            breakout_status = "Breakout"
        elif distance_to_breakout_percent <= 1.5:
            breakout_status = "About to breakout"
        else:
            breakout_status = "Weak"

    else: # direction == "SELL"
        # Calculate entry price for short
        entry_price = current_price if current_price <= breakdown_level else breakdown_level
        # Stop Loss strictly within 1.0% to 1.5%, say 1.2% above entry
        stop_loss = _round(entry_price * 1.012)
        # Targets based on realistic 1.5% profit potential
        target_1 = _round(entry_price * 0.985)
        target_2 = _round(entry_price * 0.970)
        
        expected_profit_percent = _round(((current_price - target_1) / current_price) * 100) if current_price > 0 else 0.0
        expected_loss_percent = _round(((stop_loss - current_price) / current_price) * 100) if current_price > 0 else 0.0
        risk_reward_ratio = _round(expected_profit_percent / expected_loss_percent) if expected_loss_percent > 0 else 0.0
        distance_to_breakout_percent = _round(((current_price - breakdown_level) / current_price) * 100) if current_price > breakdown_level else 0.0
        remaining_upside_percent = expected_profit_percent

        # Breakdown status
        if current_price <= breakdown_level:
            breakout_status = "Falling Breakdown"
        elif distance_to_breakout_percent <= 1.5:
            breakout_status = "About to breakdown"
        else:
            breakout_status = "Weak"

    # Explicit keys for SELL setup
    sell_entry_price = current_price if current_price <= breakdown_level else breakdown_level
    sell_stop_loss = _round(sell_entry_price * 1.012)
    downside_target_1 = _round(sell_entry_price * 0.985)
    downside_target_2 = _round(sell_entry_price * 0.970)
    expected_downside_profit_percent = _round(((current_price - downside_target_1) / current_price) * 100) if current_price > downside_target_1 else 0.0
    sell_risk_percent = _round(((sell_stop_loss - current_price) / current_price) * 100) if sell_stop_loss > current_price else 0.0
    sell_risk_reward_ratio = _round(expected_downside_profit_percent / sell_risk_percent) if sell_risk_percent > 0.0 else 0.0
    distance_to_breakdown_percent = _round(((current_price - breakdown_level) / current_price) * 100) if current_price > breakdown_level else 0.0
    support_break = bool(current_price <= breakdown_level)
    price_below_vwap = bool(current_price < vwap)
    bearish_volume_confirmation = bool(volume_vs_avg >= 2.0)
    lower_high_lower_low = bool(trend == "Bearish" or _trend_pattern(close, high, low) == "Lower High Lower Low")
    remaining_downside_percent = expected_downside_profit_percent

    # --- Market Condition Logic ---
    if volume_vs_avg < 0.75:
        market_condition = "Weak Volume"
    elif abs(already_moved_percent) > 3.5:
        market_condition = "Already Moved"
    elif rsi > 75 or rsi < 25:
        market_condition = "Volatile"
    elif trend == "Sideways" or abs(already_moved_percent) < 0.5:
        market_condition = "Sideways"
    elif direction == "BUY":
        if current_price >= breakout_level:
            market_condition = "About To Breakout"
        elif distance_to_breakout_percent <= 0.5:
            market_condition = "Near Resistance"
        elif distance_from_vwap_percent <= 0.4:
            market_condition = "Near Support"
        else:
            market_condition = "About To Breakout" if distance_to_breakout_percent <= 1.5 else "Sideways"
    else: # direction == "SELL"
        if current_price <= breakdown_level:
            market_condition = "Falling Breakdown"
        elif distance_to_breakout_percent <= 0.5:
            market_condition = "Near Support"
        elif distance_from_vwap_percent <= 0.4:
            market_condition = "Near Resistance"
        else:
            market_condition = "Falling Breakdown" if distance_to_breakout_percent <= 1.5 else "Sideways"

    # --- Quality Score Computation ---
    if direction == "BUY":
        score_trend = 0
        if current_price > ema20 > ema50:
            score_trend += 20
        elif current_price > ema200:
            score_trend += 10
        
        score_vol = 20 if volume_vs_avg >= 2.0 else (10 if volume_vs_avg >= 1.25 else 5)
        score_vwap = 15 if current_price >= vwap else -10
        score_rr = 15 if risk_reward_ratio >= 1.8 else 5
        score_upside = 15 if remaining_upside_percent >= 1.5 else 5
        score_rsi = 10 if 50 <= rsi <= 70 else (-5 if (rsi < 42 or rsi > 75) else 0)
        
        nifty_bullish = False
        if benchmark is not None and not benchmark.empty and "Close" in benchmark:
            bench_close = benchmark["Close"].astype(float)
            if len(bench_close) >= 20:
                b_ema20 = bench_close.ewm(span=20, adjust=False).mean().iloc[-1]
                nifty_bullish = bench_close.iloc[-1] > b_ema20
        score_market = 10 if nifty_bullish else 0
        penalty_overextended = -20 if (already_moved_percent > 3.5 or distance_from_intraday_high_percent < 0.4) else 0
        quality_score = max(0, min(100, 30 + score_trend + score_vol + score_vwap + score_rr + score_upside + score_rsi + score_market + penalty_overextended))
    else: # direction == "SELL"
        score_trend = 0
        if current_price < ema20 < ema50:
            score_trend += 20
        elif current_price < ema200:
            score_trend += 10
        
        score_vol = 20 if volume_vs_avg >= 2.0 else (10 if volume_vs_avg >= 1.25 else 5)
        score_vwap = 15 if current_price <= vwap else -10
        score_rr = 15 if risk_reward_ratio >= 1.8 else 5
        score_upside = 15 if remaining_upside_percent >= 1.5 else 5
        score_rsi = 10 if rsi <= 40 else (-5 if rsi > 65 else 0)
        
        nifty_bearish = False
        if benchmark is not None and not benchmark.empty and "Close" in benchmark:
            bench_close = benchmark["Close"].astype(float)
            if len(bench_close) >= 20:
                b_ema20 = bench_close.ewm(span=20, adjust=False).mean().iloc[-1]
                nifty_bearish = bench_close.iloc[-1] < b_ema20
        score_market = 10 if nifty_bearish else 0
        penalty_overextended = -20 if (already_moved_percent < -3.5 or distance_from_intraday_low_percent < 0.4) else 0
        penalty_oversold = -15 if rsi <= 30 else 0
        quality_score = max(0, min(100, 30 + score_trend + score_vol + score_vwap + score_rr + score_upside + score_rsi + score_market + penalty_overextended + penalty_oversold))

    if quality_score >= 90:
        quality_label = "Excellent"
    elif quality_score >= 80:
        quality_label = "Strong"
    elif quality_score >= 75:
        quality_label = "Good"
    elif quality_score >= 60:
        quality_label = "Watch"
    else:
        quality_label = "Avoid"

    # --- V50 Score Calculations ---
    # Momentum Score based on RSI
    rsi_val = float(rsi) if rsi is not None else 50.0
    momentum_score = _round(max(0.0, min(100.0, rsi_val)))

    # Liquidity Score based on average volume scaled to 100k
    avg_vol_val = float(avg_volume) if avg_volume else 0.0
    liquidity_score = _round(max(0.0, min(100.0, (avg_vol_val / 100000.0) * 100.0 if avg_vol_val < 100000 else 100.0)))

    # Volatility Score based on high-low spread
    high_low_spread = ((intraday_high - intraday_low) / intraday_low * 100.0) if intraday_low > 0 else 1.0
    volatility_score = _round(max(0.0, min(100.0, high_low_spread * 10.0)))

    # Intraday Score based on VWAP alignment, volume, and EMA9 crossover
    intraday_score_val = 30.0
    if price >= vwap:
        intraday_score_val += 30.0
    if volume_ratio >= 1.5:
        intraday_score_val += 20.0
    if price > ema9:
        intraday_score_val += 20.0
    intraday_score = _round(max(0.0, min(100.0, intraday_score_val)))

    # Swing Score based on EMA crossovers and trend
    swing_score_val = 30.0
    if ema20 > ema50:
        swing_score_val += 30.0
    if price > ema200:
        swing_score_val += 20.0
    if trend == "Bullish":
        swing_score_val += 20.0
    swing_score = _round(max(0.0, min(100.0, swing_score_val)))

    # --- V50 Setup Type ---
    if price >= breakout_level and volume_ratio >= 2.0:
        setup_type = "Breakout"
    elif price <= breakdown_level and volume_ratio >= 2.0:
        setup_type = "Breakdown"
    elif vwap > 0 and abs(price - vwap) / vwap <= 0.005:
        setup_type = "VWAP Support"
    elif rsi_val < 30:
        setup_type = "Oversold Pullback"
    elif rsi_val > 70:
        setup_type = "Overbought Mean Reversion"
    else:
        setup_type = "No Setup"

    # --- Target 3 Calculation ---
    target_3 = _round(entry_price * 1.045) if direction == "BUY" else _round(entry_price * 0.955)

    # --- Trailing Stop ---
    trailing_stop = _round(max(stop_loss, price * 0.985)) if direction == "BUY" else _round(min(stop_loss, price * 1.015))

    # --- V50 Freshness Score & Age Check ---
    import time
    age_seconds = 0.0
    updated_at_str = quote.get("updated_at")
    epoch_time_val = quote.get("epoch_time")
    
    if updated_at_str:
        try:
            cleaned_str = str(updated_at_str).replace("T", " ")
            if "." in cleaned_str:
                cleaned_str = cleaned_str.split(".")[0]
            parsed_dt = datetime.strptime(cleaned_str, "%Y-%m-%d %H:%M:%S")
            age_seconds = (datetime.now() - parsed_dt).total_seconds()
        except Exception:
            try:
                epoch = float(epoch_time_val or 0)
                if epoch > 0:
                    age_seconds = time.time() - epoch
            except Exception:
                age_seconds = 0.0
    elif epoch_time_val is not None:
        try:
            epoch = float(epoch_time_val)
            if epoch > 0:
                age_seconds = time.time() - epoch
            else:
                age_seconds = 0.0
        except Exception:
            age_seconds = 0.0
    else:
        # If both are entirely missing, treat as fresh (backwards compatible with old unit tests)
        age_seconds = 0.0

    freshness_score = max(0, min(100, int(100 - age_seconds * 3)))
    is_stale = age_seconds > 30.0

    # --- V50 Opening Range Trap Check ---
    is_opening_range = False
    now_dt = datetime.now()
    if now_dt.hour == 9 and 15 <= now_dt.minute <= 45:
        is_opening_range = True

    # --- Action / Decision State Machine ---
    avoid_reason = ""
    if direction == "BUY":
        # Candidate action based on quality score
        if quality_score >= 90:
            action_v50 = "STRONG BUY"
        elif quality_score >= 70:
            action_v50 = "BUY"
        elif quality_score >= 50:
            action_v50 = "WAIT"
        else:
            action_v50 = "AVOID"

        # Apply V50 Rules
        if action_v50 in ("STRONG BUY", "BUY"):
            # 1. Stale Data Check (highest priority structural rule)
            if is_stale:
                action_v50 = "WAIT"
                avoid_reason = f"Stale price feed: last updated {int(age_seconds)}s ago (max 30s allowed)"
            
            # 2. Opening Volatility Breakout Trap check (structural time-window rule)
            elif is_opening_range:
                if volume_ratio >= 3.0:
                    pass  # Keep BUY / STRONG BUY
                else:
                    action_v50 = "WAIT"
                    avoid_reason = "Opening range breakout trap protection (Wait until 09:45 AM unless confirmed)"

            # 3. Stop distance threshold check
            elif (abs(entry_price - stop_loss) / entry_price * 100.0 if entry_price > 0 else 0.0) > 2.0 or risk_reward_ratio < 1.2:
                stop_dist = abs(entry_price - stop_loss) / entry_price * 100.0 if entry_price > 0 else 0.0
                action_v50 = "AVOID"
                avoid_reason = f"Poor R/R: stop distance {stop_dist:.1f}% (max 2.0%) or R/R ratio {risk_reward_ratio:.1f} (min 1.2)"
            
            # 4. Volume Confirmation check
            elif action_v50 == "STRONG BUY" and volume_ratio < 2.5:
                action_v50 = "BUY"
            elif action_v50 == "BUY" and volume_ratio < 1.5:
                action_v50 = "WAIT"
                avoid_reason = f"Insufficient volume confirmation (Volume ratio {volume_ratio:.2f}x < 1.5x)"

        if action_v50 not in ("STRONG BUY", "BUY"):
            # Only apply overextended/high-distance overrides if no other high-priority data/structural rule
            # (like stale or opening range trap) has fired, and if volume ratio is low/normal.
            overridden = False
            if not is_stale and not (is_opening_range and volume_ratio < 3.0):
                if already_moved_percent > 3.5 and volume_ratio < 2.5:
                    decision = "AVOID - Already Moved"
                    action = "AVOID - Already Moved"
                    reason = f"AVOID - Already Moved: Stock has already moved more than 3.5% (moved {already_moved_percent:.2f}%)"
                    action_v50 = "AVOID"
                    overridden = True
                elif distance_from_intraday_high_percent < 0.4 and volume_ratio < 2.5:
                    decision = "AVOID - Near High"
                    action = "AVOID - Near High"
                    reason = f"AVOID - Near High: Price is near the intraday high with limited remaining upside (distance: {distance_from_intraday_high_percent:.2f}%)"
                    action_v50 = "AVOID"
                    overridden = True

            if not overridden:
                if action_v50 == "WAIT":
                    decision = "WAIT"
                    action = "WAIT"
                    reason = avoid_reason or "WAIT: awaiting setup confirmation"
                else:
                    decision = "AVOID"
                    action = "AVOID"
                    reason = avoid_reason or f"AVOID: quality score {quality_score} is below threshold"
        else:
            if action_v50 == "STRONG BUY":
                decision = "STRONG BUY"
                action = "STRONG BUY"
                reason = f"STRONG BUY: breakout confirmed with high volume at {datetime.now().strftime('%I:%M:%S %p')}"
            else: # BUY
                decision = "BUY READY"
                action = "BUY READY"
                reason = f"BUY NOW at {datetime.now().strftime('%I:%M:%S %p')}"

    else:  # direction == "SELL"
        if quality_score >= 90:
            action_v50 = "STRONG SELL"
            decision = "SELL READY"
            action = "SELL READY"
            reason = f"STRONG SELL: breakdown confirmed with high volume at {datetime.now().strftime('%I:%M:%S %p')}"
        elif quality_score >= 70:
            action_v50 = "SELL"
            decision = "SELL READY"
            action = "SELL READY"
            reason = f"SELL NOW at {datetime.now().strftime('%I:%M:%S %p')}"
        elif quality_score >= 50:
            action_v50 = "WAIT"
            decision = "WAIT"
            action = "WAIT"
            reason = avoid_reason or "WAIT: awaiting breakdown confirmation"
        else:
            action_v50 = "AVOID"
            decision = "AVOID"
            action = "AVOID"
            reason = avoid_reason or f"AVOID: quality score {quality_score} is below threshold"

    # Build master analysis output dictionary
    master_analysis = {
        "symbol": symbol,
        "overall_score": quality_score,
        "classification": quality_label,
        "confidence_percent": quality_score,
        "confidence_label": quality_label,
        "probability_of_success": quality_score,
        "final_action": decision,
        "expected_holding_period": "Intraday only",
        "component_scores": {
            "trend": score_trend,
            "momentum": score_rsi,
            "volume": score_vol,
            "breakout": score_vwap,
            "relative_strength": score_rr,
            "market_alignment": score_market,
            "risk_reward": score_rr,
        },
        "market_context": {
            "marketTrend": "Bullish" if (direction == "BUY" and nifty_bullish) or (direction == "SELL" and not nifty_bearish) else "Bearish",
            "niftyTrend": "Bullish" if (direction == "BUY" and nifty_bullish) or (direction == "SELL" and not nifty_bearish) else "Bearish",
            "sectorTrend": "Unavailable",
            "industryStrength": "Unavailable",
            "marketStrengthScore": 75 if ((direction == "BUY" and nifty_bullish) or (direction == "SELL" and nifty_bearish)) else 45,
        },
        "relative_strength": {
            "relativeStrengthScore": score_market,
            "niftyOutperformancePct": 0.0,
            "commentary": f"Nifty trend alignment: {'Bullish' if ((direction == 'BUY' and nifty_bullish) or (direction == 'SELL' and nifty_bearish)) else 'Bearish'}",
        },
        "multi_timeframe": {
            "alignmentScore": quality_score,
            "timeframes": [],
        },
        "trend_analysis": {
            "pattern": trend,
            "trendScore": score_trend,
        },
        "breakout_analysis": {
            "status": breakout_status,
            "probabilityPct": 0.0,
            "resistance": breakout_level if direction == "BUY" else breakdown_level,
            "distanceToResistancePct": distance_to_breakout_percent,
        },
        "volume_analysis": {
            "volumeStrengthScore": score_vol,
            "relativeVolume": volume_ratio,
            "obvBias": "Neutral",
        },
        "momentum_analysis": {
            "momentumScore": score_rsi,
            "rsi": rsi,
            "macd": macd,
            "ema20": ema20,
            "ema50": ema50,
            "ema200": ema200,
            "vwap": vwap,
        },
        "risk_analysis": {
            "riskRating": "Low" if quality_score >= 75 else "High",
            "atr": 0.0,
            "volatilityPct": expected_loss_percent,
            "distanceFromSupportPct": 0.0,
            "distanceFromResistancePct": distance_to_breakout_percent,
        },
        "trade_setups": {
            "intraday": {
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "target1": target_1,
                "target2": target_2,
                "target3": target_3,
                "risk_reward_ratio": risk_reward_ratio,
                "status": "trade_ready" if action in ("BUY READY", "STRONG BUY") else "no_trade",
                "reason": reason,
            },
            "swing": {
                "status": "no_trade",
            },
        },
        "ai_explanation": {
            "summary": reason,
            "bullishFactors": [reason] if action in ("BUY READY", "STRONG BUY") else [],
            "bearishFactors": [reason] if action == "AVOID" else [],
            "tradeRisks": [reason] if action == "AVOID" else [],
            "suggestedAction": decision,
            "probabilityOfSuccess": quality_score,
            "confidence": quality_score,
            "expectedHoldingPeriod": "Intraday",
        },
    }

    return {
        "status": "ok",
        "symbol": symbol,
        "generated_at": _now(),
        "stale": is_stale,
        "intraday_view": "BUY" if action in ("BUY READY", "STRONG BUY") else "WATCH" if action == "WAIT" else "AVOID",
        "swing_view": "BUY" if (action in ("BUY READY", "STRONG BUY") and quality_score >= 80) else "WATCH" if action == "WAIT" else "AVOID",
        "breakout_status": breakout_status,
        "trend": trend,
        "support_levels": support_levels[-3:],
        "resistance_levels": resistance_levels[-3:],
        
        # Scanner V50 unified recommendations
        "action": action_v50,
        "setup_type": setup_type,
        "entry": entry_price,
        "stop_loss": stop_loss,
        "target_1": target_1,
        "target_2": target_2,
        "target_3": target_3,
        "trailing_stop": trailing_stop,
        "risk_reward": risk_reward_ratio,
        "confidence": quality_score,
        "freshness_score": freshness_score,
        "volume_confirmation": "Confirmed" if volume_ratio >= 1.5 else "Unconfirmed",
        "vwap_status": "Above VWAP" if price >= vwap else "Below VWAP",
        "breakout_breakdown_status": breakout_status,
        "momentum_score": momentum_score,
        "liquidity_score": liquidity_score,
        "volatility_score": volatility_score,
        "intraday_score": intraday_score,
        "swing_score": swing_score,
        "reason": reason,
        "avoid_reason": avoid_reason,
        
        # Exact expected keys for V10 backward compatibility
        "intraday_trade_plan": {
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "target1": target_1,
            "target2": target_2,
            "risk_reward_ratio": risk_reward_ratio,
            "status": "trade_ready" if action in ("BUY READY", "STRONG BUY") else "no_trade",
            "reason": reason,
        },
        "swing_trade_plan": {
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "target1": target_1,
            "target2": target_2,
            "risk_reward_ratio": risk_reward_ratio,
            "status": "trade_ready" if action in ("BUY READY", "STRONG BUY") else "no_trade",
            "reason": reason,
        },
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "target1": target_1,
        "target2": target_2,
        "target3": target_3,
        "risk_reward_ratio": risk_reward_ratio,
        "volume_analysis": {
            "label": "Strong volume" if volume_ratio >= 1.25 else "Average volume",
            "latest_volume": int(latest_volume),
            "avg_volume": int(avg_volume),
            "relative_volume": volume_ratio
        },
        "indicators": {"rsi": rsi, "macd": macd, "ema9": ema9, "ema20": ema20, "ema50": ema50, "ema200": ema200, "vwap": vwap},
        "gap_status": {"label": gap_status, "gap_pct": _round(gap_pct)},
        "delivery_strength": "Unavailable",
        "master_analysis": master_analysis,
        
        # Quantitative metrics returned directly
        "current_price": current_price,
        "breakout_level": breakout_level if direction == "BUY" else breakdown_level,
        "expected_profit_percent": expected_profit_percent,
        "expected_loss_percent": expected_loss_percent,
        "distance_to_breakout_percent": distance_to_breakout_percent,
        "distance_from_vwap_percent": distance_from_vwap_percent,
        "volume_vs_avg": volume_vs_avg,
        "intraday_high": intraday_high if direction == "BUY" else intraday_low,
        "distance_from_intraday_high_percent": distance_from_intraday_high_percent if direction == "BUY" else distance_from_intraday_low_percent,
        "already_moved_percent": already_moved_percent,
        "remaining_upside_percent": remaining_upside_percent,
        "quality_score": quality_score,
        "quality_label": quality_label,
        "decision": decision,
        "action": action,
        "direction": direction,
        "market_condition": market_condition,
        
        # Explicit keys for short sell
        "breakdown_level": breakdown_level,
        "support_break": support_break,
        "price_below_vwap": price_below_vwap,
        "bearish_volume_confirmation": bearish_volume_confirmation,
        "lower_high_lower_low": lower_high_lower_low,
        "distance_to_breakdown_percent": distance_to_breakdown_percent,
        "downside_target_1": downside_target_1,
        "downside_target_2": downside_target_2,
        "sell_stop_loss": sell_stop_loss,
        "expected_downside_profit_percent": expected_downside_profit_percent,
        "sell_risk_percent": sell_risk_percent,
        "sell_risk_reward_ratio": sell_risk_reward_ratio,
        "remaining_downside_percent": remaining_downside_percent,
        
        "reason": reason,
        "quote": {
            **quote,
            "current_price": current_price,
            "previous_close": previous_close,
            "change": _round(change),
            "change_pct": already_moved_percent,
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
    quote_ttl: float = 3.0
    candle_ttl: float = 30.0
    analysis_ttl: float = 10.0
    background_interval: float = 5.0
    tracked_symbols: set[str] = field(default_factory=set)
    quote_cache: dict[str, CachedValue] = field(default_factory=dict)
    candle_cache: dict[tuple[str, str], CachedValue] = field(default_factory=dict)
    analysis_cache: dict[str, CachedValue] = field(default_factory=dict)
    unavailable_cache: dict[str, CachedValue] = field(default_factory=dict)
    _task: asyncio.Task | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _active_fetches: dict[str, asyncio.Task] = field(default_factory=dict, init=False)
    _active_analyses: dict[str, asyncio.Task] = field(default_factory=dict, init=False)
    last_requested_timestamps: dict[str, float] = field(default_factory=dict, init=False)

    @staticmethod
    def _recommendation(value: Any) -> str:
        upper = str(value or "AVOID").upper()
        if "STRONG BUY" in upper:
            return "STRONG BUY"
        elif "BUY" in upper:
            return "BUY"
        elif "WAIT" in upper:
            return "WAIT"
        elif "WATCH" in upper:
            return "WATCH"
        else:
            return "AVOID"

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
                # Strictly enforce Indian stocks/indices only (NSE ends with .NS, BSE ends with .BO, indices start with ^)
                if not (symbol.endswith(".NS") or symbol.endswith(".BO") or symbol.startswith("^")):
                    continue
                seen.add(symbol)
                records.append({"symbol": symbol, "exchange": exchange_from_symbol(symbol), "name": humanize_symbol(symbol)})
        return records

    def search(self, query: str, limit: int = 12) -> dict[str, Any]:
        needle = str(query or "").strip().upper()
        if not needle:
            return {"status": "ok", "query": query, "results": []}
        
        results = []
        seen_symbols = set()

        for record in self.symbol_records:
            symbol = str(record.get("symbol") or "").upper()
            name = str(record.get("name") or "").upper()
            base_symbol = symbol.rsplit(".", 1)[0]
            if needle not in symbol and needle not in base_symbol and needle not in name:
                continue
            if symbol in seen_symbols:
                continue
            seen_symbols.add(symbol)
            results.append({
                "symbol": symbol,
                "isin": symbol,
                "nse_symbol": base_symbol if symbol.endswith(".NS") else None,
                "bse_symbol": base_symbol if symbol.endswith(".BO") else None,
                "nse_ticker": symbol if symbol.endswith(".NS") else None,
                "bse_ticker": symbol if symbol.endswith(".BO") else None,
                "exchange": record.get("exchange") or exchange_from_symbol(symbol),
                "name": record.get("name") or humanize_symbol(symbol),
                "preferred_exchange": record.get("exchange") or exchange_from_symbol(symbol),
                "active_quote_source": record.get("exchange") or exchange_from_symbol(symbol),
            })
            if len(results) >= limit:
                return {"status": "ok", "query": query, "results": results}

        if results:
            return {"status": "ok", "query": query, "results": results}
        
        from ui.stock_registry import stock_registry, resolve_stock_identifier
        try:
            stock_registry.load_registry_cache()
        except Exception as exc:
            logger.debug(f"Stock search registry cache unavailable for {needle}: {exc}")
            return {"status": "ok", "query": query, "results": results}
        
        # Search locally in cache first
        for r in stock_registry.all_companies:
            isin = r.get("isin", "").upper()
            nse_symbol = r.get("nse_symbol", "").upper() if r.get("nse_symbol") else ""
            bse_symbol = r.get("bse_symbol", "").upper() if r.get("bse_symbol") else ""
            nse_ticker = r.get("nse_ticker", "").upper() if r.get("nse_ticker") else ""
            bse_ticker = r.get("bse_ticker", "").upper() if r.get("bse_ticker") else ""
            name = r.get("company_name", "").upper()
            
            # Check if query matches any identifier as substring or prefix
            if (needle in isin or 
                needle in nse_symbol or 
                needle in bse_symbol or 
                needle in nse_ticker or 
                needle in bse_ticker or 
                needle in name):
                
                symbol = r.get("nse_ticker") or r.get("bse_ticker") or r["isin"]
                if symbol in seen_symbols:
                    continue
                seen_symbols.add(symbol)
                results.append({
                    "symbol": symbol,
                    "isin": r["isin"],
                    "nse_symbol": r.get("nse_symbol"),
                    "bse_symbol": r.get("bse_symbol"),
                    "nse_ticker": r.get("nse_ticker"),
                    "bse_ticker": r.get("bse_ticker"),
                    "exchange": r.get("preferred_exchange") or "NSE",
                    "name": r.get("company_name"),
                    "preferred_exchange": r.get("preferred_exchange") or "NSE",
                    "active_quote_source": r.get("active_quote_source") or "NSE"
                })
                if len(results) >= limit:
                    break

        if not results:
            resolved = resolve_stock_identifier(needle, allow_remote=True)
            if resolved:
                results.append({
                    "symbol": resolved.get("nse_ticker") or resolved.get("bse_ticker") or resolved["isin"],
                    "isin": resolved["isin"],
                    "nse_symbol": resolved.get("nse_symbol"),
                    "bse_symbol": resolved.get("bse_symbol"),
                    "nse_ticker": resolved.get("nse_ticker"),
                    "bse_ticker": resolved.get("bse_ticker"),
                    "exchange": resolved.get("preferred_exchange") or "NSE",
                    "name": resolved.get("company_name"),
                    "preferred_exchange": resolved.get("preferred_exchange") or "NSE",
                    "active_quote_source": resolved.get("active_quote_source") or "NSE"
                })
                
        return {"status": "ok", "query": query, "results": results}

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._worker())
        try:
            from ui.realtime_feed import realtime_feed_simulator
            await realtime_feed_simulator.start()
        except Exception as exc:
            logger.error(f"Failed to start realtime_feed_simulator: {exc}")

    async def stop(self) -> None:
        try:
            from ui.realtime_feed import realtime_feed_simulator
            await realtime_feed_simulator.stop()
        except Exception as exc:
            logger.error(f"Failed to stop realtime_feed_simulator: {exc}")
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    async def _worker(self) -> None:
        await asyncio.sleep(self.background_interval)
        while True:
            now_ts = datetime.now().timestamp()

            try:
                from ui.watchlist_monitor import watchlist_monitor
                watchlist_symbols = {
                    item["isin"]
                    for item in watchlist_monitor.list_items()
                    if item.get("monitoring_enabled", True) and item.get("isin")
                }
            except Exception:
                watchlist_symbols = set()

            # Prune tracked_symbols if not in watchlist and not requested in the last 30 seconds
            active_symbols = set()
            for sym in self.tracked_symbols:
                if sym in watchlist_symbols or (now_ts - self.last_requested_timestamps.get(sym, 0.0) < 30.0):
                    active_symbols.add(sym)

            # Prune obsolete tracked symbols
            inactive_symbols = self.tracked_symbols - active_symbols
            for sym in inactive_symbols:
                self.tracked_symbols.discard(sym)

            # Ensure all monitored watchlist symbols are in tracked_symbols
            for sym in watchlist_symbols:
                self.tracked_symbols.add(sym)

            symbols = list(self.tracked_symbols)[:120]
            if not symbols:
                await asyncio.sleep(self.background_interval)
                continue

            cycle_started = datetime.now()
            symbols_count = len(symbols)
            success_count = 0
            failed_count = 0

            logger.info(f"Background stock fetch started for {symbols_count} symbols")

            semaphore = asyncio.Semaphore(15)

            async def update_symbol(symbol: str) -> None:
                nonlocal success_count, failed_count
                async with semaphore:
                    try:
                        retries = 2
                        for attempt in range(retries + 1):
                            try:
                                await self.get_stock(symbol, allow_stale=True, force_refresh=False)
                                await self.get_analysis(symbol, allow_stale=True, force_refresh=False)
                                success_count += 1
                                break
                            except Exception as exc:
                                if attempt == retries:
                                    raise
                                await asyncio.sleep(0.1)
                    except Exception as exc:
                        failed_count += 1
                        logger.warning(f"Background stock refresh failed for {symbol}: {exc}")

            if symbols:
                await asyncio.gather(*(update_symbol(sym) for sym in symbols), return_exceptions=True)

            last_updated_time = datetime.now().isoformat(timespec="seconds")
            logger.info(
                f"Completed cycle of continuous stock cache update. "
                f"fetch started: {cycle_started.isoformat(timespec='seconds')}, "
                f"symbols count: {symbols_count}, "
                f"success count: {success_count}, "
                f"failed count: {failed_count}, "
                f"last updated time: {last_updated_time}"
            )
            await asyncio.sleep(self.background_interval)

    async def _fetch_quote(self, symbol: str) -> dict[str, Any]:
        from ui.realtime_feed import realtime_feed_simulator
        cached_quote = realtime_feed_simulator.get_quote(symbol)
        if cached_quote and cached_quote.get("current_price") is not None:
            return cached_quote
        
        quote = await asyncio.to_thread(get_live_quote, symbol, True, 5)
        if not quote:
            quote = await asyncio.to_thread(self.provider.get_quote, symbol, True, 5)
        return quote or {}

    async def get_stock(self, symbol: str, allow_stale: bool = True, force_refresh: bool = False) -> dict[str, Any]:
        from ui.stock_registry import resolve_stock_identifier
        resolved = resolve_stock_identifier(symbol, allow_remote=True)
        if not resolved:
            return {"status": "error", "message": f"valid symbol required (could not resolve: {symbol})"}

        isin = resolved["isin"]
        # Record active request timestamp
        self.last_requested_timestamps[isin] = datetime.now().timestamp()

        cached = self.quote_cache.get(isin)
        now_ts = datetime.now().timestamp()
        unavailable = self.unavailable_cache.get(isin)

        if not force_refresh:
            if unavailable and now_ts - unavailable.updated_at < 300 and not (cached and allow_stale):
                return {**unavailable.data, "stale": True}
            if cached and now_ts - cached.updated_at < self.quote_ttl:
                self.tracked_symbols.add(isin)
                return cached.data

        # Request Collapsing: Coalesce concurrent fetches for the same symbol
        if isin in self._active_fetches:
            try:
                return await self._active_fetches[isin]
            except Exception:
                if cached and allow_stale:
                    return cached.data
                raise

        async def _coalesced_fetch() -> dict[str, Any]:
            ticker_to_fetch = resolved.get("nse_ticker") or resolved.get("bse_ticker") or isin
            try:
                quote_data = await asyncio.wait_for(self._fetch_quote(ticker_to_fetch), timeout=8)
                if not quote_data or quote_data.get("current_price") is None:
                    raise RuntimeError("Empty quote")
            except Exception as quote_exc:
                bse_ticker = resolved.get("bse_ticker")
                if ticker_to_fetch == resolved.get("nse_ticker") and bse_ticker:
                    logger.warning(f"Failed to fetch quote for NSE {ticker_to_fetch}, attempting BSE fallback {bse_ticker}: {quote_exc}")
                    ticker_to_fetch = bse_ticker
                    quote_data = await asyncio.wait_for(self._fetch_quote(ticker_to_fetch), timeout=8)
                else:
                    raise quote_exc
            candles_payload = await self.get_candles(isin, "1D", allow_stale=True)
            candles = candles_payload.get("candles") or []
            if not quote_data and not candles:
                raise RuntimeError("No market data returned by provider")

            # Merging / fallback for zero or unavailable values
            last_close = quote_data.get("current_price") or (candles[-1]["close"] if candles else None)
            previous = quote_data.get("previous_close") or (candles[-2]["close"] if len(candles) > 1 else last_close)

            cached_quote = cached.data.get("quote") if cached else {}
            if not last_close and cached_quote:
                last_close = cached_quote.get("current_price")
            if not previous and cached_quote:
                previous = cached_quote.get("previous_close")

            change = _number(last_close) - _number(previous)
            change_pct = change / _number(previous, 1) * 100 if previous else 0
            
            data = {
                "status": "ok",
                "symbol": ticker_to_fetch,
                "isin": isin,
                "nse_symbol": resolved.get("nse_symbol"),
                "bse_symbol": resolved.get("bse_symbol"),
                "nse_ticker": resolved.get("nse_ticker"),
                "bse_ticker": resolved.get("bse_ticker"),
                "preferred_exchange": resolved.get("preferred_exchange"),
                "active_quote_source": quote_data.get("active_quote_source") or resolved.get("active_quote_source") or "NSE",
                "fallback_reason": quote_data.get("fallback_reason") or resolved.get("fallback_reason"),
                "exchange": resolved.get("preferred_exchange") or exchange_from_symbol(ticker_to_fetch),
                "name": resolved.get("company_name") or quote_data.get("short_name") or quote_data.get("name") or (cached.data.get("name") if cached else None) or humanize_symbol(ticker_to_fetch),
                "logo": "",
                "quote": {**quote_data, "current_price": _round(last_close), "change": _round(change), "change_pct": _round(change_pct), "updated_at": _now()},
                "stale": False,
                "updated_at": _now(),
                "source": quote_data.get("source") or quote_data.get("provider") or (cached.data.get("source") if cached else "yfinance"),
            }
            self.quote_cache[isin] = CachedValue(data, datetime.now().timestamp())
            self.unavailable_cache.pop(isin, None)
            self.tracked_symbols.add(isin)

            # Sync successfully fetched quote to PostgreSQL database
            try:
                from ui.v20_store import connect, now
                db_timestamp = now()
                with connect() as conn:
                    stock_row = conn.execute("SELECT id FROM stocks WHERE symbol = ?", (isin,)).fetchone()
                    if not stock_row:
                        conn.execute(
                            """
                            INSERT INTO stocks(symbol, name, sector, industry, market_cap, created_at, updated_at)
                            VALUES(?, ?, ?, ?, ?, ?, ?)
                            """,
                            (isin, data["name"], resolved.get("sector") or "Unclassified", "", 0.0, db_timestamp, db_timestamp)
                        )
                        stock_row = conn.execute("SELECT id FROM stocks WHERE symbol = ?", (isin,)).fetchone()

                    if stock_row:
                        stock_id = stock_row["id"]
                        price = data["quote"]["current_price"]
                        change_p = data["quote"]["change_pct"]
                        vol = data["quote"].get("volume") or 0.0

                        # 1. Insert into stock_prices
                        conn.execute(
                            "INSERT INTO stock_prices(stock_id, price, change_pct, volume, price_date, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?)",
                            (stock_id, price, change_p, vol, db_timestamp[:10], db_timestamp, db_timestamp)
                        )
                        # 2. Upsert into live_quotes using isin as symbol
                        conn.execute(
                            """
                            INSERT INTO live_quotes(
                                symbol, price, previous_close, change_pct, volume, provider, market_status, 
                                open, day_high, day_low, fifty_day_average, two_hundred_day_average, 
                                year_high, year_low, market_cap, pe_ratio, dividend_yield, updated_at
                            )
                            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(symbol) DO UPDATE SET 
                              price=excluded.price, previous_close=excluded.previous_close,
                              change_pct=excluded.change_pct, volume=excluded.volume, provider=excluded.provider,
                              market_status=excluded.market_status, open=excluded.open, day_high=excluded.day_high,
                              day_low=excluded.day_low, fifty_day_average=excluded.fifty_day_average,
                              two_hundred_day_average=excluded.two_hundred_day_average, year_high=excluded.year_high,
                              year_low=excluded.year_low, market_cap=excluded.market_cap, pe_ratio=excluded.pe_ratio,
                              dividend_yield=excluded.dividend_yield, updated_at=excluded.updated_at
                            """,
                            (
                                isin,
                                price,
                                previous,
                                change_p,
                                vol,
                                data.get("source", "central-stock-data-service"),
                                "tracked",
                                data["quote"].get("open"),
                                data["quote"].get("day_high"),
                                data["quote"].get("day_low"),
                                data["quote"].get("fifty_day_average"),
                                data["quote"].get("two_hundred_day_average"),
                                data["quote"].get("year_high"),
                                data["quote"].get("year_low"),
                                data["quote"].get("market_cap"),
                                data["quote"].get("pe_ratio"),
                                data["quote"].get("dividend_yield"),
                                db_timestamp,
                            )
                        )
            except Exception as db_err:
                logger.warning(f"Failed to sync quote to PostgreSQL for {isin}: {db_err}")

            return data

        task = asyncio.create_task(_coalesced_fetch())
        self._active_fetches[isin] = task
        try:
            return await task
        except Exception as exc:
            if cached and allow_stale:
                stale = {**cached.data, "stale": True, "error": str(exc)}
                self.quote_cache[isin] = CachedValue(stale, cached.updated_at, stale=True, error=str(exc))
                return stale
            error = {
                "status": "error",
                "symbol": isin,
                "stale": True,
                "message": f"Stock data unavailable for {isin}. Symbol may be invalid, newly listed, or unavailable.",
                "provider_error": str(exc),
                "updated_at": _now(),
            }
            self.unavailable_cache[isin] = CachedValue(error, datetime.now().timestamp(), stale=True, error=str(exc))
            self.tracked_symbols.discard(isin)
            return error
        finally:
            self._active_fetches.pop(isin, None)

    async def get_candles(self, symbol: str, range_key: str = "1D", allow_stale: bool = True) -> dict[str, Any]:
        from ui.stock_registry import resolve_stock_identifier
        resolved = resolve_stock_identifier(symbol, allow_remote=True)
        if not resolved:
            return {"status": "error", "symbol": symbol, "range": range_key, "candles": [], "stale": True, "message": f"Could not resolve symbol {symbol}", "updated_at": _now()}
        
        isin = resolved["isin"]
        range_name = str(range_key or "1D").upper()
        period, interval = RANGE_MAP.get(range_name, RANGE_MAP["1D"])
        key = (isin, range_name)
        cached = self.candle_cache.get(key)
        now_ts = datetime.now().timestamp()
        if cached and now_ts - cached.updated_at < self.candle_ttl:
            return cached.data
        try:
            ticker_to_fetch = resolved.get("nse_ticker") or resolved.get("bse_ticker") or isin
            try:
                raw = await asyncio.wait_for(asyncio.to_thread(get_stock_data, ticker_to_fetch, period, interval), timeout=12)
                df = _normalize_df(raw)
                if df.empty:
                    raise RuntimeError("No candle data returned")
            except Exception as first_exc:
                bse_ticker = resolved.get("bse_ticker")
                if ticker_to_fetch == resolved.get("nse_ticker") and bse_ticker:
                    logger.warning(f"Failed to fetch candles for NSE {ticker_to_fetch}, trying BSE fallback {bse_ticker}: {first_exc}")
                    ticker_to_fetch = bse_ticker
                    raw = await asyncio.wait_for(asyncio.to_thread(get_stock_data, ticker_to_fetch, period, interval), timeout=12)
                    df = _normalize_df(raw)
                    if df.empty:
                        raise RuntimeError("No candle data returned for BSE fallback")
                else:
                    raise first_exc
            data = {
                "status": "ok",
                "symbol": ticker_to_fetch,
                "isin": isin,
                "nse_symbol": resolved.get("nse_symbol"),
                "bse_symbol": resolved.get("bse_symbol"),
                "nse_ticker": resolved.get("nse_ticker"),
                "bse_ticker": resolved.get("bse_ticker"),
                "preferred_exchange": resolved.get("preferred_exchange"),
                "active_quote_source": resolved.get("active_quote_source") or "NSE",
                "fallback_reason": resolved.get("fallback_reason"),
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
            return {"status": "error", "symbol": symbol, "range": range_name, "candles": [], "stale": True, "message": str(exc), "updated_at": _now()}

    async def auto_push_high_profit_stock(self, isin: str, analysis_data: dict[str, Any]) -> None:
        try:
            from ui.watchlist_monitor import watchlist_monitor
            if not watchlist_monitor.settings.get("auto_add_candidates", False):
                return
            if isin in watchlist_monitor.items:
                return
            
            # Check if this stock was manually deleted by the user
            nse_ticker = analysis_data.get("nse_ticker") or ""
            bse_ticker = analysis_data.get("bse_ticker") or ""
            nse_symbol = analysis_data.get("nse_symbol") or ""
            bse_symbol = analysis_data.get("bse_symbol") or ""
            norm_isin = normalize_stock_symbol(isin)
            
            if (isin in watchlist_monitor.user_deleted_symbols or 
                (norm_isin and norm_isin in watchlist_monitor.user_deleted_symbols) or
                (nse_ticker and nse_ticker.upper() in watchlist_monitor.user_deleted_symbols) or
                (bse_ticker and bse_ticker.upper() in watchlist_monitor.user_deleted_symbols) or
                (nse_symbol and nse_symbol.upper() in watchlist_monitor.user_deleted_symbols) or
                (bse_symbol and bse_symbol.upper() in watchlist_monitor.user_deleted_symbols)):
                logger.info(f"Skipping auto-promotion of {isin} because user manually deleted it from watchlist")
                return
            
            logger.info(f"Auto-promoting high-profit stock {isin} to watchlist due to BUY signal")
            await watchlist_monitor.add_item({
                "symbol": isin,
                "monitoring_enabled": True,
                "alerts_enabled": True,
                "notes": f"Auto-promoted due to BUY signal: Intraday={analysis_data.get('intraday_view')}, Swing={analysis_data.get('swing_view')}"
            })
        except Exception as e:
            logger.error(f"Error in auto_push_high_profit_stock for {isin}: {e}", exc_info=True)

    async def get_analysis(self, symbol: str, allow_stale: bool = True, force_refresh: bool = False) -> dict[str, Any]:
        from ui.stock_registry import resolve_stock_identifier
        resolved = resolve_stock_identifier(symbol, allow_remote=True)
        if not resolved:
            return {
                "status": "error",
                "symbol": symbol,
                "message": f"Could not resolve symbol {symbol}",
                "stale": True,
                "generated_at": _now(),
            }
        
        isin = resolved["isin"]
        self.last_requested_timestamps[isin] = datetime.now().timestamp()
        
        cached = self.analysis_cache.get(isin)
        now_ts = datetime.now().timestamp()
        unavailable = self.unavailable_cache.get(isin)
        
        if not force_refresh:
            if unavailable and now_ts - unavailable.updated_at < 300 and not cached:
                return {
                    "status": "error",
                    "symbol": isin,
                    "message": unavailable.data.get("message") or "Stock data unavailable",
                    "stale": True,
                    "generated_at": _now(),
                }
            if cached and now_ts - cached.updated_at < self.analysis_ttl:
                return self._analysis_response(cached.data, cached.updated_at, True)

        if isin in self._active_analyses:
            try:
                return await self._active_analyses[isin]
            except Exception:
                if cached and allow_stale:
                    return self._analysis_response(cached.data, cached.updated_at, True)
                raise

        async def _coalesced_analyze() -> dict[str, Any]:
            stock = await self.get_stock(isin, allow_stale=allow_stale, force_refresh=force_refresh)
            if stock.get("status") == "error" and not stock.get("quote"):
                raise RuntimeError(stock.get("message") or f"Stock data unavailable for {isin}")
            quote = stock.get("quote") or {}
            historical_payload = {}
            for range_key in ("6M", "3M", "1M", "1W", "1D"):
                historical_payload = await self.get_candles(isin, range_key, allow_stale=True)
                if historical_payload.get("candles"):
                    break
            intraday_payload = {}
            for range_key in ("1D", "1W"):
                intraday_payload = await self.get_candles(isin, range_key, allow_stale=True)
                if intraday_payload.get("candles"):
                    break
            if not (historical_payload.get("candles") or intraday_payload.get("candles")):
                raise RuntimeError(f"No candle data available for {isin}")
            benchmark_payload = await self.get_candles("^NSEI", "6M", allow_stale=True)
            historical = pd.DataFrame(historical_payload.get("candles") or [])
            intraday = pd.DataFrame(intraday_payload.get("candles") or [])
            benchmark = pd.DataFrame(benchmark_payload.get("candles") or [])
            for df in (historical, intraday, benchmark):
                if not df.empty:
                    df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}, inplace=True)
            
            ticker_for_analysis = resolved.get("nse_ticker") or resolved.get("bse_ticker") or isin
            data = build_rule_analysis(ticker_for_analysis, quote, historical, intraday, benchmark)
            data["stock"] = stock
            data["isin"] = isin
            data["nse_symbol"] = resolved.get("nse_symbol")
            data["bse_symbol"] = resolved.get("bse_symbol")
            data["nse_ticker"] = resolved.get("nse_ticker")
            data["bse_ticker"] = resolved.get("bse_ticker")
            data["preferred_exchange"] = resolved.get("preferred_exchange")
            data["active_quote_source"] = quote.get("active_quote_source") or resolved.get("active_quote_source") or "NSE"
            data["fallback_reason"] = quote.get("fallback_reason") or resolved.get("fallback_reason")
            
            data["stale"] = bool(stock.get("stale") or historical_payload.get("stale") or intraday_payload.get("stale") or benchmark_payload.get("stale"))
            self.analysis_cache[isin] = CachedValue(data, datetime.now().timestamp())
            
            intraday_view = data.get("intraday_view")
            swing_view = data.get("swing_view")
            if intraday_view == "BUY" or swing_view == "BUY":
                asyncio.create_task(
                    self.auto_push_high_profit_stock(isin, data),
                    name=f"auto-push-{isin}"
                )
            
            return self._analysis_response(data, datetime.now().timestamp(), False)

        task = asyncio.create_task(_coalesced_analyze())
        self._active_analyses[isin] = task
        try:
            return await task
        except Exception as exc:
            if cached and allow_stale:
                stale = {**cached.data, "stale": True, "error": str(exc)}
                self.analysis_cache[isin] = CachedValue(stale, cached.updated_at, stale=True, error=str(exc))
                return self._analysis_response(stale, cached.updated_at, True)
            message = str(exc)
            error = {
                "status": "error",
                "symbol": isin,
                "message": message,
                "stale": True,
                "generated_at": _now(),
            }
            self.unavailable_cache[isin] = CachedValue(error, datetime.now().timestamp(), stale=True, error=message)
            self.tracked_symbols.discard(isin)
            return error
        finally:
            self._active_analyses.pop(isin, None)


stock_data_service = CentralStockDataService(Path(__file__).resolve().parent.parent)


async def encode_sse(event: str, payload: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n".encode("utf-8")

