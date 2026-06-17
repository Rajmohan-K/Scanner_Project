from __future__ import annotations

from typing import Any

import yfinance as yf

from config import FUNDAMENTAL_CACHE_TTL
from data.cache_utils import load_cache, save_cache
from data.yfinance_utils import ensure_yfinance_cache
from utils.logger import logger


def _as_pct(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        value = float(value)
        return value * 100 if abs(value) <= 2 else value
    except Exception:
        return 0.0


def _as_float(value: Any) -> float:
    try:
        return float(value if value is not None else 0)
    except Exception:
        return 0.0


def get_fundamental_data(symbol: str) -> dict[str, Any]:
    """
    Fetch real fundamental fields from yfinance when available.
    Missing values remain neutral and are marked with data_quality.
    """

    cache_key = f"{symbol}|fundamentals"
    cached = load_cache("fundamentals", cache_key, FUNDAMENTAL_CACHE_TTL)
    if isinstance(cached, dict) and cached:
        return cached.copy()

    try:
        ensure_yfinance_cache()
        ticker = yf.Ticker(symbol)
        try:
            info = ticker.info or {}
        except Exception:
            info = {}

        if not info:
            return {"source": "unavailable", "data_quality": "missing"}

        data = {
            "revenue_growth": _as_pct(info.get("revenueGrowth")),
            "profit_growth": _as_pct(info.get("earningsQuarterlyGrowth") or info.get("earningsGrowth")),
            "eps_growth": _as_pct(info.get("earningsGrowth")),
            "roe": _as_pct(info.get("returnOnEquity")),
            "roce": _as_pct(info.get("returnOnAssets")),
            "debt_to_equity": _as_float(info.get("debtToEquity")) / 100,
            "current_ratio": _as_float(info.get("currentRatio")),
            "pe_ratio": _as_float(info.get("trailingPE") or info.get("forwardPE")),
            "pb_ratio": _as_float(info.get("priceToBook")),
            "promoter_holding": _as_pct(info.get("heldPercentInsiders")),
            "market_cap": _as_float(info.get("marketCap")),
            "source": "yfinance_info",
            "data_quality": "real",
        }
        if not any(data.get(key, 0) for key in ["revenue_growth", "profit_growth", "roe", "pe_ratio", "pb_ratio"]):
            data["data_quality"] = "partial"

        save_cache("fundamentals", cache_key, data)
        return data

    except Exception as exc:
        logger.error(f"Fundamental data failed for {symbol}: {exc}")
        return {"source": "error", "data_quality": "missing"}
