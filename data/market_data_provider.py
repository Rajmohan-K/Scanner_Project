from __future__ import annotations
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*timedelta.*")
import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
from data.direct_feeds import fetch_market_news_feed, fetch_stock_news_feed

from data.market_data import (
    _extract_scalar_or_default,
    get_live_quote,
    get_stock_data,
    normalize_market_symbol,
    resolve_groww_token,
)
from data.yfinance_utils import ensure_yfinance_cache, get_yfinance_session
from utils.logger import logger

_SHORT_NAME_CACHE: dict[str, str] = {}


class MarketDataProvider(ABC):
    @abstractmethod
    def get_indices(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_quote(self, symbol: str, use_cache: bool = True, ttl: int | None = None) -> dict[str, Any]:
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
            quote = self.get_quote(symbol, use_cache=True, ttl=15)
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

    def get_quote(self, symbol: str, use_cache: bool = True, ttl: int | None = None) -> dict[str, Any]:
        normalized = normalize_market_symbol(symbol)
        if not normalized:
            return {}
        from config import QUOTE_CACHE_TTL
        actual_ttl = ttl if ttl is not None else QUOTE_CACHE_TTL
        quote = get_live_quote(normalized, use_cache=use_cache, ttl=actual_ttl)
        if not quote:
            return {}
        short_name = _SHORT_NAME_CACHE.get(normalized)
        if not short_name and use_cache:
            try:
                ensure_yfinance_cache()
                import yfinance as yf
                info = yf.Ticker(normalized, session=get_yfinance_session()).fast_info or {}
                short_name = getattr(info, "get", lambda *_: None)("shortName")
                if short_name:
                    _SHORT_NAME_CACHE[normalized] = short_name
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
        df = get_stock_data(symbol, period=period, interval=interval, ignore_provider=True)
        if df is None or df.empty:
            return []
        records: list[dict[str, Any]] = []
        for index, row in df.tail(500).iterrows():
            records.append(
                {
                    "time": index.isoformat() if hasattr(index, "isoformat") else str(index),
                    "open": _extract_scalar_or_default(row.get("Open"), 0.0),
                    "high": _extract_scalar_or_default(row.get("High"), 0.0),
                    "low": _extract_scalar_or_default(row.get("Low"), 0.0),
                    "close": _extract_scalar_or_default(row.get("Close"), 0.0),
                    "volume": _extract_scalar_or_default(row.get("Volume"), 0.0),
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
            import yfinance as yf
            info = yf.Ticker(normalized, session=get_yfinance_session()).info or {}
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


GROWW_INTERVAL_MAP = {
    "1m": "1minute",
    "5m": "5minute",
    "15m": "15minute",
    "30m": "30minute",
    "1h": "1hour",
    "1d": "1day",
    "1D": "1day",
    "1w": "1week",
    "1wk": "1week",
    "1mo": "1month",
}


class GrowwProvider(MarketDataProvider):
    def __init__(self) -> None:
        self.yf_provider = YahooFinanceProvider()

    def _get_groww_symbol_info(self, symbol: str) -> tuple[str, str, str] | None:
        # Skip indices for Groww historical/intraday fetches
        if symbol and symbol.startswith("^"):
            return None

        from ui.stock_registry import resolve_stock_identifier
        resolved = resolve_stock_identifier(symbol, allow_remote=False)
        if not resolved:
            trading_symbol = symbol.split(".")[0]
            exchange = "NSE"
        else:
            trading_symbol = resolved.get("nse_symbol")
            exchange = "NSE"
            if not trading_symbol:
                trading_symbol = resolved.get("bse_symbol")
                exchange = "BSE"
            if not trading_symbol:
                trading_symbol = symbol.split(".")[0]
                exchange = "NSE"
            
        try:
            from ui.storage import load_settings
            settings = load_settings()
            api_token = resolve_groww_token(settings)
            if not api_token:
                return trading_symbol, exchange, trading_symbol

            from growwapi import GrowwAPI
            api = GrowwAPI(api_token)
            api._load_instruments()
            
            inst = api.get_instrument_by_exchange_and_trading_symbol(exchange, trading_symbol)
            groww_symbol = inst.get("groww_symbol")
            if groww_symbol:
                return trading_symbol, exchange, groww_symbol
        except Exception as e:
            logger.debug(f"Could not resolve groww_symbol for {symbol}: {e}")
            
        return trading_symbol, exchange, trading_symbol


    def _fetch_groww_candles(self, symbol: str, period: str, interval: str) -> list[dict[str, Any]]:
        info = self._get_groww_symbol_info(symbol)
        if not info:
            return []
            
        trading_symbol, exchange, groww_symbol = info
        
        # Calculate dates
        import re
        from datetime import datetime, timedelta
        end = datetime.now()
        match = re.match(r"^(\d+)([a-z]+)$", period.lower())
        if not match:
            start = end - timedelta(days=180)
        else:
            amount = int(match.group(1))
            unit = match.group(2)
            if unit == "d":
                start = end - timedelta(days=amount)
            elif unit == "w":
                start = end - timedelta(weeks=amount)
            elif unit == "mo":
                start = end - timedelta(days=amount * 30.5)
            elif unit == "y":
                start = end - timedelta(days=amount * 365)
            else:
                start = end - timedelta(days=180)

        start_str = start.strftime("%Y-%m-%d %H:%M:%S")
        end_str = end.strftime("%Y-%m-%d %H:%M:%S")
        
        candle_interval = GROWW_INTERVAL_MAP.get(interval, "1day")
        
        try:
            from ui.storage import load_settings
            settings = load_settings()
            api_token = resolve_groww_token(settings)
            if not api_token:
                return []

            from growwapi import GrowwAPI
            api = GrowwAPI(api_token)
            
            res = api.get_historical_candles(
                exchange=exchange,
                segment="CASH",
                groww_symbol=groww_symbol,
                start_time=start_str,
                end_time=end_str,
                candle_interval=candle_interval
            )
            
            payload = res.get("payload") or {}
            candles_list = payload.get("candles") or []
            
            records = []
            for candle in candles_list:
                if len(candle) >= 6:
                    ts = candle[0]
                    dt = datetime.fromtimestamp(ts)
                    records.append({
                        "time": dt.isoformat(),
                        "open": float(candle[1]),
                        "high": float(candle[2]),
                        "low": float(candle[3]),
                        "close": float(candle[4]),
                        "volume": float(candle[5]),
                    })
            return records
        except Exception as e:
            logger.warning(f"Failed to fetch Groww historical candles for {symbol}: {e}")
            return []

    def get_indices(self) -> list[dict[str, Any]]:
        return self.yf_provider.get_indices()


    def get_quote(self, symbol: str, use_cache: bool = True, ttl: int | None = None) -> dict[str, Any]:
        normalized = normalize_market_symbol(symbol)
        if not normalized:
            return {}
        from config import QUOTE_CACHE_TTL
        actual_ttl = ttl if ttl is not None else QUOTE_CACHE_TTL
        
        quote = get_live_quote(normalized, use_cache=use_cache, ttl=actual_ttl)
        if not quote:
            return {}
            
        return {
            **quote,
            "symbol": normalized,
            "short_name": quote.get("company_name") or normalized,
            "provider": quote.get("source", "groww"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }

    def get_historical_prices(self, symbol: str, period: str = "6mo", interval: str = "1d") -> list[dict[str, Any]]:
        res = self._fetch_groww_candles(symbol, period, interval)
        if res:
            return res
        logger.debug(f"Groww historical candles failed/empty for {symbol}; returning no candles in non-Yahoo mode")
        return []

    def get_intraday_prices(self, symbol: str, interval: str = "5m") -> list[dict[str, Any]]:
        res = self._fetch_groww_candles(symbol, "5d", interval)
        if res:
            return res
        logger.debug(f"Groww intraday candles failed/empty for {symbol}; returning no candles in non-Yahoo mode")
        return []

    def get_financial_metrics(self, symbol: str) -> dict[str, Any]:
        return self.yf_provider.get_financial_metrics(symbol)

    def get_news(self, symbol: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        return self.yf_provider.get_news(symbol, limit)


_GLOBAL_PROVIDER_INSTANCE: MarketDataProvider | None = None
_GLOBAL_PROVIDER_NAME: str | None = None

def get_market_data_provider() -> MarketDataProvider:
    global _GLOBAL_PROVIDER_INSTANCE, _GLOBAL_PROVIDER_NAME
    try:
        from ui.storage import load_settings
        settings = load_settings()
        provider_name = settings.get("feed_provider")
    except Exception:
        provider_name = None

    if not provider_name:
        provider_name = os.getenv("MARKET_DATA_PROVIDER", "yfinance").strip().lower()
        
    provider_name = provider_name.strip().lower()
    
    # Return cached singleton instance if it exists and matches requested provider
    if _GLOBAL_PROVIDER_INSTANCE is not None and _GLOBAL_PROVIDER_NAME == provider_name:
        return _GLOBAL_PROVIDER_INSTANCE
        
    if provider_name in ("yfinance", "cached-yfinance", "yahoo"):
        _GLOBAL_PROVIDER_INSTANCE = YahooFinanceProvider()
    elif provider_name in ("kotak", "kotakneo", "kotak-neo", "kotak_neo"):
        logger.warning("Kotak Neo is disabled for live market data. Redirecting to YahooFinanceProvider.")
        _GLOBAL_PROVIDER_INSTANCE = YahooFinanceProvider()
    elif provider_name == "groww":
        logger.warning("Groww is disabled for live market data. Redirecting to YahooFinanceProvider.")
        _GLOBAL_PROVIDER_INSTANCE = YahooFinanceProvider()
    else:
        logger.warning(f"Unsupported or default MARKET_DATA_PROVIDER={provider_name}; defaulting to YahooFinanceProvider")
        _GLOBAL_PROVIDER_INSTANCE = YahooFinanceProvider()
        
    _GLOBAL_PROVIDER_NAME = provider_name
    return _GLOBAL_PROVIDER_INSTANCE
