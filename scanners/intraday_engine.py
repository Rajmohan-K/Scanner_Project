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
    
    from scanners.centralized_analysis_engine import centralized_analysis_engine
    analysis = centralized_analysis_engine.analyze(symbol, quote, df, df)
    
    score = analysis.get("quality_score", 35)
    signal = "BUY" if score >= V30_INTRADAY_MIN_BUY_SCORE else "WATCH" if score >= V30_INTRADAY_MIN_WATCH_SCORE else "AVOID"
    
    ltp = analysis.get("current_price") or quote.get("current_price") or df["Close"].iloc[-1]
    previous_close = analysis.get("previous_close") or quote.get("previous_close") or (df["Close"].iloc[-2] if len(df) > 1 else df["Close"].iloc[-1])
    
    row = {
        **analysis,
        "stock": symbol,
        "symbol": symbol,
        "sector": "Intraday",
        "ltp": ltp,
        "live_price": ltp,
        "last_close": previous_close,
        "open": analysis.get("open") or quote.get("open") or df["Open"].iloc[-1] if "Open" in df else ltp,
        "high": df["High"].iloc[-1] if "High" in df else ltp,
        "low": df["Low"].iloc[-1] if "Low" in df else ltp,
        "volume": int(df["Volume"].iloc[-1]) if "Volume" in df and len(df) > 0 else 0,
        "score": score,
        "technical_score": score,
        "intraday_score": score,
        "confidence_pct": analysis.get("confidence") or score,
        "ml_probability": analysis.get("confidence") or score,
        "profitability_score": score,
        "quality_score": score,
        "risk_score": analysis.get("risk_score") or 50.0,
        "signal": signal,
        "grade": signal,
        "trade_type": "BUY" if signal == "BUY" else "WATCH" if signal == "WATCH" else "NO_TRADE",
        "premarket_action": signal,
        "final_decision": "Trade" if signal == "BUY" else "Watch" if signal == "WATCH" else "No Trade",
        "best_horizon": "Intraday",
        "entry": analysis.get("entry") or ltp,
        "entry_price": analysis.get("entry") or ltp,
        "stoploss": analysis.get("stop_loss") or (ltp * 0.98),
        "stop_loss": analysis.get("stop_loss") or (ltp * 0.98),
        "target1": analysis.get("target1") or (ltp * 1.02),
        "target2": analysis.get("target2") or (ltp * 1.04),
        "target3": analysis.get("target3") or (ltp * 1.06),
        "risk_reward": analysis.get("risk_reward_ratio") or 2.0,
        "reason": analysis.get("reason") or "",
        "reason_selected": analysis.get("reason") if signal in ("BUY", "WATCH") else "",
        "reason_rejected": "" if signal in ("BUY", "WATCH") else analysis.get("reason"),
        "scan_mode": "intraday",
        "scan_family": "intraday",
        "scanner_bucket": "intraday",
        "pipeline_stage": "quick_signal",
    }
    
    return {
        "status": "ok",
        "symbol": symbol,
        "row": row,
        "interval": interval,
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
