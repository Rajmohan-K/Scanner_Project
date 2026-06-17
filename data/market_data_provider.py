from __future__ import annotations

import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import yfinance as yf

from data.direct_feeds import fetch_market_news_feed, fetch_stock_news_feed
from data.market_data import get_live_quote, get_stock_data, normalize_market_symbol
from data.yfinance_utils import ensure_yfinance_cache
from utils.logger import logger


class MarketDataProvider(ABC):
    @abstractmethod
    def get_indices(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_quote(self, symbol: str, use_cache: bool = True) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_historical_prices(self, symbol: str, period: str = "6mo", interval: str = "1d") -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_intraday_prices(self, symbol: str, interval: str = "5m") -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_financial_metrics(self, symbol: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_news(self, symbol: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        raise NotImplementedError


class YahooFinanceProvider(MarketDataProvider):
    def __init__(self) -> None:
        self.index_symbols = [
            item.strip()
            for item in os.getenv("MARKET_INDEX_SYMBOLS", "^NSEI,^BSESN").split(",")
            if item.strip()
        ]

    def get_indices(self) -> list[dict[str, Any]]:
        indices: list[dict[str, Any]] = []
        for symbol in self.index_symbols:
            quote = self.get_quote(symbol, use_cache=False)
            price = quote.get("current_price")
            if price is None:
                continue
            previous = quote.get("previous_close")
            change_pct = 0.0
            if previous:
                change_pct = ((float(price) - float(previous)) / float(previous)) * 100
            indices.append(
                {
                    "symbol": symbol,
                    "name": quote.get("short_name") or symbol,
                    "value": float(price),
                    "change_pct": round(change_pct, 2),
                    "source": "yfinance",
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
        return indices

    def get_quote(self, symbol: str, use_cache: bool = True) -> dict[str, Any]:
        normalized = normalize_market_symbol(symbol)
        if not normalized:
            return {}
        quote = get_live_quote(normalized, use_cache=use_cache)
        if not quote:
            return {}
        short_name = None
        if use_cache:
            try:
                ensure_yfinance_cache()
                info = yf.Ticker(normalized).fast_info or {}
                short_name = getattr(info, "get", lambda *_: None)("shortName")
            except Exception:
                short_name = None
        return {
            **quote,
            "symbol": normalized,
            "short_name": short_name or normalized,
            "provider": "yfinance",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }

    def get_historical_prices(self, symbol: str, period: str = "6mo", interval: str = "1d") -> list[dict[str, Any]]:
        df = get_stock_data(symbol, period=period, interval=interval)
        if df is None or df.empty:
            return []
        records: list[dict[str, Any]] = []
        for index, row in df.tail(500).iterrows():
            records.append(
                {
                    "time": index.isoformat() if hasattr(index, "isoformat") else str(index),
                    "open": float(row.get("Open", 0) or 0),
                    "high": float(row.get("High", 0) or 0),
                    "low": float(row.get("Low", 0) or 0),
                    "close": float(row.get("Close", 0) or 0),
                    "volume": float(row.get("Volume", 0) or 0),
                }
            )
        return records

    def get_intraday_prices(self, symbol: str, interval: str = "5m") -> list[dict[str, Any]]:
        return self.get_historical_prices(symbol, period="5d", interval=interval)

    def get_financial_metrics(self, symbol: str) -> dict[str, Any]:
        normalized = normalize_market_symbol(symbol)
        if not normalized:
            return {}
        try:
            ensure_yfinance_cache()
            info = yf.Ticker(normalized).info or {}
        except Exception as exc:
            logger.debug(f"Financial metrics unavailable for {symbol}: {exc}")
            return {}

        def number(*keys: str) -> float | None:
            for key in keys:
                value = info.get(key)
                if value is None:
                    continue
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
            return None

        return {
            "symbol": normalized,
            "market_cap": number("marketCap"),
            "pe": number("trailingPE", "forwardPE"),
            "roe": number("returnOnEquity"),
            "roce": number("returnOnCapital"),
            "eps_growth": number("earningsQuarterlyGrowth"),
            "revenue_growth": number("revenueGrowth"),
            "net_profit_margin": number("profitMargins"),
            "debt_ratio": number("debtToEquity"),
            "free_cash_flow": number("freeCashflow"),
            "dividend_yield": number("dividendYield"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "name": info.get("longName") or info.get("shortName"),
            "source": "yfinance",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }

    def get_news(self, symbol: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        return fetch_stock_news_feed(symbol, limit=limit) if symbol else fetch_market_news_feed(limit=limit)


def get_market_data_provider() -> MarketDataProvider:
    provider_name = os.getenv("MARKET_DATA_PROVIDER", "yfinance").strip().lower()
    if provider_name != "yfinance":
        logger.warning(f"Unsupported MARKET_DATA_PROVIDER={provider_name}; using yfinance adapter")
    return YahooFinanceProvider()
