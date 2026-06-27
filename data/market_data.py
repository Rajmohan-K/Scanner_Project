import re
from typing import Any
import warnings
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*timedelta.*")


def _extract_scalar(value: Any) -> float | None:
    if value is None:
        return None
    import pandas as pd
    while isinstance(value, (pd.Series, pd.DataFrame)):
        if value.empty:
            return None
        value = value.iloc[0]
    try:
        import math
        val = float(value)
        return val if math.isfinite(val) else None
    except (TypeError, ValueError):
        return None


def _extract_scalar_or_default(value: Any, default: float = 0.0) -> float:
    res = _extract_scalar(value)
    return res if res is not None else default

from config import MARKET_DATA_CACHE_TTL, QUOTE_CACHE_TTL
from data.cache_utils import load_cache, save_cache
from data.yfinance_utils import ensure_yfinance_cache, get_yfinance_session
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


def slice_dataframe_period(df, period, interval):
    """
    Slices a pandas DataFrame relative to its last timestamp,
    returning a subset matching the requested period (e.g. '5d', '6mo', '1y').
    """
    if df is None or df.empty:
        return pd.DataFrame()

    if period.lower() in ("max", "all", "ytd"):
        return df.copy()

    import re
    from datetime import timedelta

    match = re.match(r"^(\d+)([a-z]+)$", period.lower())
    if not match:
        return df.copy()

    amount = int(match.group(1))
    unit = match.group(2)
    last_timestamp = df.index[-1]

    if unit == "d":
        delta = timedelta(days=amount)
    elif unit == "w":
        delta = timedelta(weeks=amount)
    elif unit == "mo":
        delta = timedelta(days=amount * 30.5)
    elif unit == "y":
        delta = timedelta(days=amount * 365)
    else:
        delta = timedelta(days=amount)

    start_time = last_timestamp - delta
    return df.loc[df.index >= start_time].copy()


def _fetch_raw_stock_data(symbol, period="6mo", interval="1d"):
    symbol = normalize_market_symbol(symbol)
    if not symbol:
        return pd.DataFrame()

    try:
        ensure_yfinance_cache()
        unified_key = f"{symbol}|{interval}"
        
        fresh_df = load_cache("ohlcv", unified_key, MARKET_DATA_CACHE_TTL)
        if isinstance(fresh_df, pd.DataFrame) and not fresh_df.empty:
            return slice_dataframe_period(fresh_df, period, interval)

        cached_df = load_cache("ohlcv", unified_key, -1)
        query_period = "5d" if (isinstance(cached_df, pd.DataFrame) and not cached_df.empty) else period

        try:
            import yfinance as yf
            df = yf.download(
                tickers=symbol,
                period=query_period,
                interval=interval,
                progress=False,
                session=get_yfinance_session()
            )
        except Exception as download_err:
            logger.warning(f"Download failed for {symbol}: {download_err}. Using cache fallback.")
            df = pd.DataFrame()

        if df.empty:
            if isinstance(cached_df, pd.DataFrame) and not cached_df.empty:
                return slice_dataframe_period(cached_df, period, interval)
            return pd.DataFrame()

        df.dropna(inplace=True)

        if isinstance(cached_df, pd.DataFrame) and not cached_df.empty:
            merged_df = pd.concat([cached_df, df])
            merged_df = merged_df[~merged_df.index.duplicated(keep="last")]
            merged_df.sort_index(inplace=True)
        else:
            merged_df = df

        save_cache("ohlcv", unified_key, merged_df)
        return slice_dataframe_period(merged_df, period, interval)

    except Exception as e:
        logger.error(f"Market data fetch failed for raw symbol {symbol}: {e}")
        try:
            cached_df = load_cache("ohlcv", f"{symbol}|{interval}", -1)
            if isinstance(cached_df, pd.DataFrame) and not cached_df.empty:
                return slice_dataframe_period(cached_df, period, interval)
        except Exception:
            pass
        return pd.DataFrame()


def get_stock_data(symbol, period="6mo", interval="1d"):
    """
    Fetch OHLCV stock market data with dynamic NSE/BSE fallback.
    """
    from ui.stock_registry import resolve_stock_identifier
    resolved = resolve_stock_identifier(symbol, allow_remote=True)
    if not resolved:
        logger.warning(f"Rejected invalid stock symbol for get_stock_data: {symbol}")
        return pd.DataFrame()

    nse_ticker = resolved.get("nse_ticker")
    bse_ticker = resolved.get("bse_ticker")
    
    if nse_ticker:
        try:
            df = _fetch_raw_stock_data(nse_ticker, period, interval)
            if df is not None and not df.empty:
                return df
        except Exception as e:
            logger.warning(f"NSE candle fetch failed for {nse_ticker}, attempting BSE: {e}")

    if bse_ticker:
        try:
            df = _fetch_raw_stock_data(bse_ticker, period, interval)
            if df is not None and not df.empty:
                return df
        except Exception as e:
            logger.warning(f"BSE candle fetch fallback failed for {bse_ticker}: {e}")

    return pd.DataFrame()


def get_bulk_stock_data(
    symbols,
    period="6mo",
    interval="1d",
    batch_size=75,
    should_cancel=None,
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
        
        cached_histories = {}
        uncached_symbols = []

        for symbol in symbol_list:
            unified_key = f"{symbol}|{interval}"
            fresh_df = load_cache("ohlcv", unified_key, MARKET_DATA_CACHE_TTL)
            if isinstance(fresh_df, pd.DataFrame) and not fresh_df.empty:
                frames[symbol] = slice_dataframe_period(fresh_df, period, interval)
            else:
                uncached_symbols.append(symbol)
                cached_df = load_cache("ohlcv", unified_key, -1)
                if isinstance(cached_df, pd.DataFrame) and not cached_df.empty:
                    cached_histories[symbol] = cached_df

        if not uncached_symbols:
            return frames

        query_period = "5d" if cached_histories else period

        for start in range(0, len(uncached_symbols), batch_size):
            if should_cancel and should_cancel():
                logger.info("Bulk stock fetch cancelled cooperatively between batches")
                break
            batch = uncached_symbols[start:start + batch_size]

            try:
                raw = yf.download(
                    tickers=batch,
                    period=query_period,
                    interval=interval,
                    progress=False,
                    group_by="ticker",
                    threads=True,
                    auto_adjust=False,
                    session=get_yfinance_session(),
                )
            except Exception as exc:
                logger.error(f"Bulk market data fetch failed for batch starting {start}: {exc}")
                for symbol in batch:
                    if symbol in cached_histories:
                        frames[symbol] = slice_dataframe_period(cached_histories[symbol], period, interval)
                continue

            if raw is None or raw.empty:
                for symbol in batch:
                    if symbol in cached_histories:
                        frames[symbol] = slice_dataframe_period(cached_histories[symbol], period, interval)
                continue

            if isinstance(raw.columns, pd.MultiIndex):
                for symbol in batch:
                    if symbol not in raw.columns.get_level_values(0):
                        if symbol in cached_histories:
                            frames[symbol] = slice_dataframe_period(cached_histories[symbol], period, interval)
                        else:
                            frames[symbol] = pd.DataFrame()
                        continue
                    
                    symbol_df = raw[symbol].copy()
                    symbol_df.dropna(how="all", inplace=True)
                    
                    cached_df = cached_histories.get(symbol)
                    if isinstance(cached_df, pd.DataFrame) and not cached_df.empty and not symbol_df.empty:
                        merged_df = pd.concat([cached_df, symbol_df])
                        merged_df = merged_df[~merged_df.index.duplicated(keep="last")]
                        merged_df.sort_index(inplace=True)
                    else:
                        merged_df = symbol_df if not symbol_df.empty else (cached_df if cached_df is not None else pd.DataFrame())

                    if not merged_df.empty:
                        save_cache("ohlcv", f"{symbol}|{interval}", merged_df)
                        frames[symbol] = slice_dataframe_period(merged_df, period, interval)
                    else:
                        frames[symbol] = pd.DataFrame()
            else:
                batch_symbol = batch[0]
                single_df = raw.copy()
                single_df.dropna(how="all", inplace=True)
                
                cached_df = cached_histories.get(batch_symbol)
                if isinstance(cached_df, pd.DataFrame) and not cached_df.empty and not single_df.empty:
                    merged_df = pd.concat([cached_df, single_df])
                    merged_df = merged_df[~merged_df.index.duplicated(keep="last")]
                    merged_df.sort_index(inplace=True)
                else:
                    merged_df = single_df if not single_df.empty else (cached_df if cached_df is not None else pd.DataFrame())

                if not merged_df.empty:
                    save_cache("ohlcv", f"{batch_symbol}|{interval}", merged_df)
                    frames[batch_symbol] = slice_dataframe_period(merged_df, period, interval)
                else:
                    frames[batch_symbol] = pd.DataFrame()

        return frames

    except Exception as exc:
        logger.error(f"Bulk market data failed: {exc}")
        fallback = {}
        for symbol in symbols:
            normalized = normalize_market_symbol(symbol)
            if normalized:
                cached_df = load_cache("ohlcv", f"{normalized}|{interval}", -1)
                if isinstance(cached_df, pd.DataFrame) and not cached_df.empty:
                    fallback[normalized] = slice_dataframe_period(cached_df, period, interval)
        return fallback


def _fetch_raw_quote_data(symbol, use_cache=True, ttl=QUOTE_CACHE_TTL):
    symbol = normalize_market_symbol(symbol)
    if not symbol:
        return {}
    cache_key = f"{symbol}|quote"

    try:
        ensure_yfinance_cache()
        cached_quote = load_cache("quotes", cache_key, ttl) if use_cache else None
        if use_cache and isinstance(cached_quote, dict) and cached_quote:
            return cached_quote.copy()

        import yfinance as yf
        ticker = yf.Ticker(symbol, session=get_yfinance_session())
        try:
            fast_info = ticker.fast_info
            if fast_info is None or not hasattr(fast_info, "get"):
                fast_info = {}
        except Exception as exc:
            logger.warning(f"Failed to get fast_info for {symbol}: {exc}")
            fast_info = {}

        current_price = fast_info.get("lastPrice") if hasattr(fast_info, "get") else None
        open_price = fast_info.get("open") if hasattr(fast_info, "get") else None
        prev_close = fast_info.get("previousClose") if hasattr(fast_info, "get") else None
        day_high = fast_info.get("dayHigh") if hasattr(fast_info, "get") else None
        day_low = fast_info.get("dayLow") if hasattr(fast_info, "get") else None
        volume = fast_info.get("volume") if hasattr(fast_info, "get") else None
        fifty_day_average = fast_info.get("fiftyDayAverage") if hasattr(fast_info, "get") else None
        two_hundred_day_average = fast_info.get("twoHundredDayAverage") if hasattr(fast_info, "get") else None
        year_high = fast_info.get("yearHigh") if hasattr(fast_info, "get") else None
        year_low = fast_info.get("yearLow") if hasattr(fast_info, "get") else None
        market_cap = fast_info.get("marketCap") if hasattr(fast_info, "get") else None

        pe_ratio = None
        dividend_yield = None

        quote = {
            "current_price": _extract_scalar(current_price),
            "open": _extract_scalar(open_price),
            "previous_close": _extract_scalar(prev_close),
            "day_high": _extract_scalar(day_high),
            "day_low": _extract_scalar(day_low),
            "volume": _extract_scalar(volume),
            "fifty_day_average": _extract_scalar(fifty_day_average),
            "two_hundred_day_average": _extract_scalar(two_hundred_day_average),
            "year_high": _extract_scalar(year_high),
            "year_low": _extract_scalar(year_low),
            "market_cap": _extract_scalar(market_cap),
            "pe_ratio": _extract_scalar(pe_ratio),
            "dividend_yield": _extract_scalar(dividend_yield),
            "source": "yfinance",
        }
        if use_cache and current_price is not None:
            save_cache("quotes", cache_key, quote)
        return quote

    except Exception as e:
        logger.debug(f"Live quote provider failed for {symbol}: {e}")
        return {}


def get_live_quote(symbol, use_cache=True, ttl=QUOTE_CACHE_TTL):
    """
    Fetch a stock quote with dynamic NSE/BSE fallback.
    """
    if symbol and str(symbol).strip().startswith("^"):
        try:
            quote = _fetch_raw_quote_data(symbol, use_cache=use_cache, ttl=ttl)
            if quote and quote.get("current_price") is not None:
                quote["active_quote_source"] = "INDEX"
                quote["company_name"] = symbol
                return quote
        except Exception as e:
            logger.warning(f"Index fetch failed for {symbol}: {e}")
        return {}

    from ui.stock_registry import resolve_stock_identifier
    resolved = resolve_stock_identifier(symbol, allow_remote=True)
    if not resolved:
        logger.warning(f"Rejected invalid stock symbol for get_live_quote: {symbol}")
        return {}

    nse_ticker = resolved.get("nse_ticker")
    bse_ticker = resolved.get("bse_ticker")
    
    quote = {}
    
    if nse_ticker:
        try:
            quote = _fetch_raw_quote_data(nse_ticker, use_cache=use_cache, ttl=ttl)
            if quote and quote.get("current_price") is not None:
                quote["active_quote_source"] = "NSE"
                quote["nse_symbol"] = resolved.get("nse_symbol")
                quote["bse_symbol"] = resolved.get("bse_symbol")
                quote["isin"] = resolved.get("isin")
                quote["company_name"] = resolved.get("company_name")
                return quote
        except Exception as e:
            logger.warning(f"NSE quote fetch failed for {nse_ticker}, attempting BSE fallback: {e}")

    if bse_ticker:
        try:
            quote = _fetch_raw_quote_data(bse_ticker, use_cache=use_cache, ttl=ttl)
            if quote and quote.get("current_price") is not None:
                quote["active_quote_source"] = "BSE"
                quote["fallback_reason"] = "NSE quote unavailable" if nse_ticker else "NSE symbol missing"
                quote["nse_symbol"] = resolved.get("nse_symbol")
                quote["bse_symbol"] = resolved.get("bse_symbol")
                quote["isin"] = resolved.get("isin")
                quote["company_name"] = resolved.get("company_name")
                return quote
        except Exception as e:
            logger.warning(f"BSE quote fallback failed for {bse_ticker}: {e}")

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


def is_groww_token_restricted(token: str) -> bool:
    if not token or not isinstance(token, str):
        return True
    parts = token.split(".")
    if len(parts) != 3:
        return False
    try:
        import base64
        import json
        payload_b64 = parts[1]
        payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
        if payload.get("role") == "auth-totp":
            return True
    except Exception:
        pass
    return False


_cached_groww_token = None
_cached_key_secret_hash = None


def resolve_groww_token(settings):
    global _cached_groww_token, _cached_key_secret_hash
    import os
    
    # 1. Check if user configured access token directly
    direct_token = os.getenv("GROWW_ACCESS_TOKEN")
    if direct_token:
        if is_groww_token_restricted(direct_token):
            logger.warning("GROWW_ACCESS_TOKEN has restricted 'auth-totp' role. Quotes and candles will be fetched from yfinance.")
            return None
        return direct_token
        
    # 2. Check if they have GROWW_API_KEY / GROWW_API_TOKEN
    api_key = os.getenv("GROWW_API_KEY") or os.getenv("GROWW_API_TOKEN") or settings.get("groww_api_key")
    api_secret = os.getenv("GROWW_API_SECRET") or settings.get("groww_api_secret")
    
    if not api_key:
        return None
        
    # If they only gave API key without secret
    if not api_secret:
        if is_groww_token_restricted(api_key):
            logger.warning("Groww API Key is an auth-totp token. Please configure the Groww API Secret to dynamically generate a full access token.")
            return None
        return api_key
        
    # If they gave both key and secret, fetch the access token dynamically
    key_secret_hash = f"{api_key}|{api_secret}"
    if _cached_groww_token and _cached_key_secret_hash == key_secret_hash:
        return _cached_groww_token
        
    try:
        from growwapi import GrowwAPI
        access_token = GrowwAPI.get_access_token(api_key=api_key, secret=api_secret)
        _cached_groww_token = access_token
        _cached_key_secret_hash = key_secret_hash
        logger.info("Successfully fetched Groww access token dynamically using API Key & Secret.")
        return access_token
    except Exception as e:
        logger.error(f"Failed to dynamically generate Groww access token: {e}")
        return None
