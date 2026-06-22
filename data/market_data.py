import re

import pandas as pd
import yfinance as yf

from config import MARKET_DATA_CACHE_TTL, QUOTE_CACHE_TTL
from data.cache_utils import load_cache, save_cache
from data.yfinance_utils import ensure_yfinance_cache
from utils.logger import logger

VALID_SYMBOL_RE = re.compile(r"^\^?[A-Z0-9\.\-_]+$")
INVALID_SYMBOLS = {"UNDEFINED", "NONE", "N/A", "NA", "NULL", "UNKNOWN"}


def normalize_market_symbol(symbol):
    if symbol is None:
        return None
    value = str(symbol).strip().upper()
    if not value or value in INVALID_SYMBOLS or not VALID_SYMBOL_RE.match(value):
        return None
    return value


def get_stock_data(
    symbol,
    period="6mo",
    interval="1d"
):
    """
    Fetch OHLCV stock market data.
    """

    raw_symbol = symbol
    symbol = normalize_market_symbol(symbol)
    if not symbol:
        logger.warning(f"Rejected invalid stock symbol for get_stock_data: {raw_symbol}")
        return pd.DataFrame()

    try:
        ensure_yfinance_cache()
        cache_key = f"{symbol}|{period}|{interval}"
        cached_df = load_cache("ohlcv", cache_key, MARKET_DATA_CACHE_TTL)
        if isinstance(cached_df, pd.DataFrame) and not cached_df.empty:
            return cached_df.copy()

        df = yf.download(
            tickers=symbol,
            period=period,
            interval=interval,
            progress=False
        )

        if df.empty:

            raise ValueError(
                f"No data found for {symbol}"
            )

        df.dropna(inplace=True)
        save_cache("ohlcv", cache_key, df)

        return df

    except Exception as e:

        logger.error(
            f"Market data fetch failed: {e}"
        )

        return pd.DataFrame()


def get_bulk_stock_data(
    symbols,
    period="6mo",
    interval="1d",
    batch_size=75,
):
    """
    Fetch OHLCV data for many symbols in batches.
    """

    try:
        ensure_yfinance_cache()
        frames = {}
        symbol_list = []
        for symbol in symbols:
            normalized = normalize_market_symbol(symbol)
            if normalized:
                symbol_list.append(normalized)
            else:
                logger.warning(f"Dropped invalid bulk stock symbol: {symbol}")
        uncached_symbols = []

        for symbol in symbol_list:
            cache_key = f"{symbol}|{period}|{interval}"
            cached_df = load_cache("ohlcv", cache_key, MARKET_DATA_CACHE_TTL)
            if isinstance(cached_df, pd.DataFrame) and not cached_df.empty:
                frames[symbol] = cached_df.copy()
            else:
                uncached_symbols.append(symbol)

        for start in range(0, len(uncached_symbols), batch_size):
            batch = uncached_symbols[start:start + batch_size]

            try:
                raw = yf.download(
                    tickers=batch,
                    period=period,
                    interval=interval,
                    progress=False,
                    group_by="ticker",
                    threads=True,
                    auto_adjust=False,
                )
            except Exception as exc:
                logger.error(f"Bulk market data fetch failed for batch starting {start}: {exc}")
                continue

            if raw is None or raw.empty:
                continue

            if isinstance(raw.columns, pd.MultiIndex):
                for symbol in batch:
                    if symbol not in raw.columns.get_level_values(0):
                        frames[symbol] = pd.DataFrame()
                        continue
                    symbol_df = raw[symbol].copy()
                    symbol_df.dropna(how="all", inplace=True)
                    frames[symbol] = symbol_df
                    if not symbol_df.empty:
                        save_cache("ohlcv", f"{symbol}|{period}|{interval}", symbol_df)
            else:
                batch_symbol = batch[0]
                single_df = raw.copy()
                single_df.dropna(how="all", inplace=True)
                frames[batch_symbol] = single_df
                if not single_df.empty:
                    save_cache("ohlcv", f"{batch_symbol}|{period}|{interval}", single_df)

        return frames

    except Exception as exc:
        logger.error(f"Bulk market data failed: {exc}")
        return {}


def get_live_quote(symbol, use_cache=True):
    raw_symbol = symbol
    symbol = normalize_market_symbol(symbol)
    if not symbol:
        logger.warning(f"Rejected invalid stock symbol for get_live_quote: {raw_symbol}")
        return {}
    cache_key = f"{symbol}|quote"

    try:
        ensure_yfinance_cache()
        cached_quote = load_cache("quotes", cache_key, QUOTE_CACHE_TTL) if use_cache else None
        if use_cache and isinstance(cached_quote, dict) and cached_quote:
            return cached_quote.copy()

        ticker = yf.Ticker(symbol)
        try:
            fast_info = ticker.fast_info
            if fast_info is None or not hasattr(fast_info, "get"):
                fast_info = {}
        except Exception as exc:
            logger.warning(f"Failed to get fast_info for {symbol}: {exc}")
            fast_info = {}

        # Fallback values from fast_info if available
        current_price = fast_info.get("lastPrice") if hasattr(fast_info, "get") else None
        open_price = fast_info.get("open") if hasattr(fast_info, "get") else None
        prev_close = fast_info.get("previousClose") if hasattr(fast_info, "get") else None
        day_high = fast_info.get("dayHigh") if hasattr(fast_info, "get") else None
        day_low = fast_info.get("dayLow") if hasattr(fast_info, "get") else None

        info = {}
        if use_cache:
            try:
                info = ticker.info or {}
            except Exception:
                info = {}

        # If fast_info failed or doesn't have core prices, fetch a small history as robust fallback
        if not current_price or not open_price or not prev_close:
            try:
                history = ticker.history(period="5d", interval="1d")
                if history is not None and not history.empty:
                    if not current_price:
                        current_price = float(history["Close"].iloc[-1])
                    if not open_price:
                        open_price = float(history["Open"].iloc[-1])
                    if not prev_close:
                        prev_close = float(history["Close"].iloc[-2]) if len(history) >= 2 else current_price
                    if not day_high:
                        day_high = float(history["High"].iloc[-1])
                    if not day_low:
                        day_low = float(history["Low"].iloc[-1])
            except Exception as history_exc:
                logger.warning(f"Failed to fetch history fallback in get_live_quote for {symbol}: {history_exc}")

        # Fallback to info dict if still missing
        if not current_price:
            try:
                if not info:
                    info = ticker.info or {}
                current_price = info.get("currentPrice") or info.get("regularMarketPrice")
                if not open_price:
                    open_price = info.get("open") or info.get("regularMarketOpen")
                if not prev_close:
                    prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
                if not day_high:
                    day_high = info.get("dayHigh") or info.get("regularMarketDayHigh")
                if not day_low:
                    day_low = info.get("dayLow") or info.get("regularMarketDayLow")
            except Exception as info_exc:
                logger.warning(f"Failed to fetch info fallback in get_live_quote for {symbol}: {info_exc}")

        quote = {
            "current_price": current_price,
            "open": open_price,
            "previous_close": prev_close,
            "day_high": day_high or (info.get("dayHigh") if info else None),
            "day_low": day_low or (info.get("dayLow") if info else None),
            "source": "yfinance",
        }
        if use_cache and current_price is not None:
            save_cache("quotes", cache_key, quote)
        return quote

    except Exception as e:
        logger.warning(f"Live quote provider failed for {symbol}: {e}")
        fallback_df = get_stock_data(symbol, period="5d", interval="1d")
        if fallback_df is not None and not fallback_df.empty:
            fallback_df = fallback_df.dropna()
            if not fallback_df.empty:
                last = fallback_df.iloc[-1]
                previous = fallback_df.iloc[-2] if len(fallback_df) >= 2 else last
                quote = {
                    "current_price": float(last.get("Close", 0) or 0),
                    "open": float(last.get("Open", 0) or 0),
                    "previous_close": float(previous.get("Close", 0) or 0),
                    "day_high": float(last.get("High", 0) or 0),
                    "day_low": float(last.get("Low", 0) or 0),
                    "source": "yfinance_history_fallback",
                    "stale": True,
                }
                if use_cache:
                    save_cache("quotes", cache_key, quote)
                return quote
        return {}


def get_live_price(symbol):

    try:
        quote = get_live_quote(symbol)
        return quote.get("current_price")

    except Exception as e:

        logger.error(
            f"Live price failed: {e}"
        )

        return None
