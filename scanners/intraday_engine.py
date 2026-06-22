from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from config import (
    V30_CANDLE_CACHE_SECONDS,
    V30_INTRADAY_ANALYSIS_CACHE_SECONDS,
    V30_INTRADAY_ATR_STOP_MULTIPLIER,
    V30_INTRADAY_MIN_BUY_SCORE,
    V30_INTRADAY_MIN_WATCH_SCORE,
    V30_INTRADAY_PERIOD,
    V30_INTRADAY_TARGET_1R,
    V30_INTRADAY_TARGET_2R,
    V30_INTRADAY_TARGET_3R,
    V30_QUOTE_CACHE_SECONDS,
)
from data.market_data import get_live_quote, get_stock_data


@dataclass
class CacheItem:
    value: Any
    created_at: float


_QUOTE_CACHE: dict[str, CacheItem] = {}
_CANDLE_CACHE: dict[str, CacheItem] = {}
_ANALYSIS_CACHE: dict[str, CacheItem] = {}


def _fresh(cache: dict[str, CacheItem], key: str, ttl: float) -> Any | None:
    item = cache.get(key)
    if not item:
        return None
    if time.time() - item.created_at > ttl:
        return None
    return item.value


def _store(cache: dict[str, CacheItem], key: str, value: Any) -> Any:
    cache[key] = CacheItem(value=value, created_at=time.time())
    return value


def _normalize_symbol(symbol: str) -> str:
    cleaned = str(symbol or "").strip().upper().replace(" ", "")
    if not cleaned:
        return ""
    return cleaned if "." in cleaned else f"{cleaned}.NS"


def _round(value: Any, digits: int = 2, default: float = 0.0) -> float:
    try:
        return round(float(value if value is not None else default), digits)
    except (TypeError, ValueError):
        return default


def _normalize_frame(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if hasattr(df.columns, "nlevels") and getattr(df.columns, "nlevels", 1) > 1:
        if symbol in df.columns.get_level_values(0):
            df = df[symbol].copy()
        elif symbol in df.columns.get_level_values(-1):
            df = df.xs(symbol, axis=1, level=-1).copy()
        else:
            df = df.copy()
            df.columns = [column[-1] if isinstance(column, tuple) else column for column in df.columns]
    return df.copy()


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    previous_close = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    atr = _atr(high, low, close, period).replace(0, pd.NA)
    plus_di = 100 * plus_dm.rolling(period).mean() / atr
    minus_di = 100 * minus_dm.rolling(period).mean() / atr
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, pd.NA)) * 100
    return dx.rolling(period).mean()


def _supertrend_line(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 10, multiplier: float = 3.0) -> pd.Series:
    atr = _atr(high, low, close, period).fillna((high - low).rolling(period).mean())
    hl2 = (high + low) / 2
    upper = hl2 + multiplier * atr
    lower = hl2 - multiplier * atr
    return lower.where(close >= _ema(close, period), upper)


def _fetch_quote(symbol: str) -> tuple[dict[str, Any], bool]:
    key = symbol.upper()
    cached = _fresh(_QUOTE_CACHE, key, V30_QUOTE_CACHE_SECONDS)
    if cached is not None:
        return cached, True
    quote = get_live_quote(symbol, use_cache=True) or {}
    if not quote:
        quote = get_live_quote(symbol, use_cache=False) or {}
    return _store(_QUOTE_CACHE, key, quote), False


def _fetch_candles(symbol: str, interval: str) -> tuple[pd.DataFrame, bool]:
    key = f"{symbol.upper()}:{interval}"
    cached = _fresh(_CANDLE_CACHE, key, V30_CANDLE_CACHE_SECONDS)
    if cached is not None:
        return cached, True
    period = V30_INTRADAY_PERIOD if str(interval).endswith("m") else "30d"
    df = get_stock_data(symbol, period=period, interval=interval)
    if df is None or df.empty:
        raise ValueError(f"intraday candles unavailable for {symbol}")
    return _store(_CANDLE_CACHE, key, _normalize_frame(df, symbol)), False


def quick_intraday_signal(symbol: str, interval: str = "5m") -> dict[str, Any]:
    started = time.perf_counter()
    quote, quote_cached = _fetch_quote(symbol)
    df, candles_cached = _fetch_candles(symbol, interval)
    recent = df.tail(120).copy()
    close = recent["Close"].astype(float)
    high = recent["High"].astype(float)
    low = recent["Low"].astype(float)
    open_ = recent["Open"].astype(float) if "Open" in recent else close
    volume = recent["Volume"].astype(float) if "Volume" in recent else close * 0

    ema9 = _ema(close, 9)
    ema20 = _ema(close, 20)
    ema12 = _ema(close, 12)
    ema26 = _ema(close, 26)
    macd = ema12 - ema26
    macd_signal = _ema(macd, 9)
    rsi = _rsi(close, 14)
    atr = _atr(high, low, close, 14)
    adx = _adx(high, low, close, 14)
    supertrend = _supertrend_line(high, low, close)

    typical = (high + low + close) / 3
    volume_sum = float(volume.tail(60).sum() or 0)
    vwap = float((typical.tail(60) * volume.tail(60)).sum() / volume_sum) if volume_sum else float(close.tail(20).mean())
    avg_volume = float(volume.tail(30).mean() or 0)
    current_volume = float(volume.iloc[-1] or 0)
    relative_volume = current_volume / avg_volume if avg_volume else 1.0
    ltp = _round(quote.get("current_price") or quote.get("regularMarketPrice") or close.iloc[-1])
    previous_close = _round(quote.get("previous_close") or (close.iloc[-2] if len(close) > 1 else close.iloc[-1]))
    day_change_pct = ((ltp - previous_close) / previous_close * 100) if previous_close else 0.0
    momentum_pct = ((ltp - float(close.iloc[-6])) / float(close.iloc[-6]) * 100) if len(close) >= 6 and close.iloc[-6] else 0.0
    atr_value = float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) else max(float((high.tail(14) - low.tail(14)).mean() or 0), ltp * 0.0075)
    support = float(low.tail(20).min())
    resistance = float(high.tail(20).max())

    signals_passed: list[str] = []
    signals_failed: list[str] = []
    checks = {
        "LTP above VWAP": ltp >= vwap,
        "EMA 9 above EMA 20": float(ema9.iloc[-1]) >= float(ema20.iloc[-1]),
        "MACD above signal": float(macd.iloc[-1]) >= float(macd_signal.iloc[-1]),
        "RSI constructive": 45 <= float(rsi.iloc[-1] if pd.notna(rsi.iloc[-1]) else 50) <= 72,
        "ADX trend strength": float(adx.iloc[-1] if pd.notna(adx.iloc[-1]) else 0) >= 18,
        "Supertrend supportive": ltp >= float(supertrend.iloc[-1]),
        "Relative volume active": relative_volume >= 1.15,
        "Positive day/momentum": day_change_pct >= 0 or momentum_pct >= 0,
    }
    for label, passed in checks.items():
        (signals_passed if passed else signals_failed).append(label)

    score = 35
    score += 10 if checks["LTP above VWAP"] else -6
    score += 10 if checks["EMA 9 above EMA 20"] else -6
    score += 9 if checks["MACD above signal"] else -5
    score += 8 if checks["RSI constructive"] else -5
    score += 8 if checks["ADX trend strength"] else 0
    score += 8 if checks["Supertrend supportive"] else -6
    score += min(max((relative_volume - 1) * 12, -8), 18)
    score += min(max(momentum_pct * 2.5, -10), 15)
    score += 6 if ltp >= resistance * 0.998 else 0
    score = max(0, min(100, score))

    signal = "BUY" if score >= V30_INTRADAY_MIN_BUY_SCORE else "WATCH" if score >= V30_INTRADAY_MIN_WATCH_SCORE else "AVOID"
    entry = ltp if signal != "AVOID" else 0.0
    stoploss = max(support, entry - (atr_value * V30_INTRADAY_ATR_STOP_MULTIPLIER)) if entry else 0.0
    risk = max(entry - stoploss, atr_value, 0.01) if entry else 0.0
    target1 = entry + risk * V30_INTRADAY_TARGET_1R if entry else 0.0
    target2 = entry + risk * V30_INTRADAY_TARGET_2R if entry else 0.0
    target3 = entry + risk * V30_INTRADAY_TARGET_3R if entry else 0.0
    selected = signal != "AVOID"
    reason = (
        f"{signal}: score {score:.0f}/100, VWAP {vwap:.2f}, EMA9 {ema9.iloc[-1]:.2f}, "
        f"EMA20 {ema20.iloc[-1]:.2f}, RSI {_round(rsi.iloc[-1])}, rel vol {relative_volume:.2f}x."
    )
    if not selected:
        reason += f" Rejected because failed signals: {', '.join(signals_failed[:4]) or 'insufficient confirmation'}."

    row = {
        "stock": symbol,
        "symbol": symbol,
        "sector": "Intraday",
        "ltp": ltp,
        "live_price": ltp,
        "last_close": previous_close,
        "open": _round(quote.get("open") or open_.iloc[-1]),
        "high": _round(high.iloc[-1]),
        "low": _round(low.iloc[-1]),
        "volume": int(current_volume),
        "vwap": _round(vwap),
        "ema9": _round(ema9.iloc[-1]),
        "ema20": _round(ema20.iloc[-1]),
        "rsi": _round(rsi.iloc[-1]),
        "macd": _round(macd.iloc[-1]),
        "macd_signal": _round(macd_signal.iloc[-1]),
        "adx": _round(adx.iloc[-1]),
        "atr": _round(atr_value),
        "supertrend": _round(supertrend.iloc[-1]),
        "relative_volume": _round(relative_volume),
        "volume_spike": relative_volume >= 1.5,
        "day_change_pct": _round(day_change_pct),
        "momentum_pct": _round(momentum_pct),
        "score": _round(score),
        "technical_score": _round(score),
        "intraday_score": _round(score),
        "confidence_pct": _round(min(95, max(20, score + len(signals_passed) * 2))),
        "ml_probability": _round(min(95, max(20, score + momentum_pct))),
        "profitability_score": _round(score),
        "quality_score": _round(min(100, 40 + len(signals_passed) * 7 + min(relative_volume, 3) * 5)),
        "risk_score": _round(max(5, min(90, (risk / max(entry, 1)) * 1000 if entry else 70))),
        "signal": signal,
        "grade": signal,
        "trade_type": "BUY" if signal == "BUY" else "WATCH" if signal == "WATCH" else "NO_TRADE",
        "premarket_action": signal,
        "final_decision": "Trade" if signal == "BUY" else "Watch" if signal == "WATCH" else "No Trade",
        "best_horizon": "Intraday",
        "setup_type": "VWAP/EMA momentum" if selected else "No trade",
        "entry": _round(entry),
        "entry_price": _round(entry),
        "stoploss": _round(stoploss),
        "stop_loss": _round(stoploss),
        "target1": _round(target1),
        "target2": _round(target2),
        "target3": _round(target3),
        "risk_reward": _round((target2 - entry) / risk if entry and risk else 0),
        "expected_return": _round(((target1 - entry) / entry * 100) if entry else 0),
        "reason": reason,
        "reason_selected": reason if selected else "",
        "reason_rejected": "" if selected else reason,
        "signals_passed": signals_passed,
        "signals_failed": signals_failed,
        "data_timestamp": datetime.now().isoformat(timespec="seconds"),
        "scan_mode": "intraday",
        "scan_family": "intraday",
        "scanner_bucket": "intraday",
        "pipeline_stage": "quick_signal",
    }
    return {
        "status": "ok",
        "symbol": symbol,
        "interval": interval,
        "row": row,
        "data_state": "cached" if quote_cached and candles_cached else "fresh",
        "stale": False,
        "quote_cached": quote_cached,
        "candles_cached": candles_cached,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def cached_quick_intraday_signal(symbol: str, interval: str = "5m", cache_seconds: int | None = None) -> dict[str, Any]:
    normalized = _normalize_symbol(symbol)
    if not normalized:
        raise ValueError("valid symbol required")
    ttl = V30_INTRADAY_ANALYSIS_CACHE_SECONDS if cache_seconds is None else max(0, int(cache_seconds))
    key = f"{normalized}:{interval}"
    cached = _fresh(_ANALYSIS_CACHE, key, ttl) if ttl else None
    if cached is not None:
        row = dict(cached.get("row") or {})
        row["analysis_cached"] = True
        payload = {**cached, "row": row, "data_state": "cached_analysis", "analysis_cached": True}
        return payload
    payload = quick_intraday_signal(normalized, interval)
    row = dict(payload.get("row") or {})
    row["analysis_cached"] = False
    payload = {**payload, "row": row, "analysis_cached": False}
    _store(_ANALYSIS_CACHE, key, payload)
    return payload


def analyze_intraday_symbols(
    symbols: list[str] | tuple[str, ...],
    interval: str = "5m",
    source: str = "manual",
    cache_seconds: int | None = None,
    max_workers: int = 4,
) -> dict[str, Any]:
    started = time.perf_counter()
    normalized_symbols = list(dict.fromkeys(_normalize_symbol(symbol) for symbol in symbols))
    normalized_symbols = [symbol for symbol in normalized_symbols if symbol]
    rows: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    cached_symbols: list[str] = []
    analyzed_symbols: list[str] = []

    def analyze_one(symbol: str) -> dict[str, Any]:
        before = _fresh(_ANALYSIS_CACHE, f"{symbol}:{interval}", V30_INTRADAY_ANALYSIS_CACHE_SECONDS if cache_seconds is None else max(0, int(cache_seconds)))
        payload = cached_quick_intraday_signal(symbol, interval=interval, cache_seconds=cache_seconds)
        return {**payload, "_was_cached": before is not None}

    worker_count = max(1, min(int(max_workers or 1), 8, len(normalized_symbols) or 1))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(analyze_one, symbol): symbol for symbol in normalized_symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                payload = future.result()
                row = dict(payload.get("row") or {})
                if not row:
                    failures.append({"symbol": symbol, "message": "empty intraday engine result"})
                    continue
                row.update(
                    {
                        "symbol": row.get("symbol") or symbol,
                        "stock": row.get("stock") or symbol,
                        "source": source,
                        "analysis_source": "IntradayScannerService",
                        "scan_mode": "intraday",
                        "scan_family": "intraday",
                        "scanner_bucket": "intraday",
                        "pipeline_stage": f"{source}_quick_signal" if source != "manual" else "quick_signal",
                        "selected_scan_type": "intraday",
                        "data_state": payload.get("data_state"),
                        "analysis_cached": bool(payload.get("_was_cached") or payload.get("analysis_cached")),
                    }
                )
                all_rows.append(row)
                if row["analysis_cached"]:
                    cached_symbols.append(symbol)
                else:
                    analyzed_symbols.append(symbol)
                if str(row.get("signal") or row.get("trade_type") or "").upper() in {"BUY", "WATCH"}:
                    rows.append(row)
            except Exception as exc:
                failures.append({"symbol": symbol, "message": str(exc)})

    rows.sort(key=lambda item: (float(item.get("intraday_score") or item.get("score") or 0), float(item.get("relative_volume") or 0)), reverse=True)
    all_rows.sort(key=lambda item: (float(item.get("intraday_score") or item.get("score") or 0), float(item.get("relative_volume") or 0)), reverse=True)
    return {
        "status": "ok",
        "source": source,
        "interval": interval,
        "symbols": normalized_symbols,
        "source_count": len(normalized_symbols),
        "rows": rows,
        "all_rows": all_rows,
        "cached_symbols": cached_symbols,
        "analyzed_symbols": analyzed_symbols,
        "failed": failures,
        "cache_seconds": V30_INTRADAY_ANALYSIS_CACHE_SECONDS if cache_seconds is None else int(cache_seconds),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "message": f"{len(rows)} intraday opportunities, {len(analyzed_symbols)} newly analyzed, {len(cached_symbols)} served from cache.",
    }
