import pandas as pd
import requests
import yfinance as yf

from config import OPTIONS_CACHE_TTL
from data.cache_utils import load_cache, save_cache
from data.yfinance_utils import ensure_yfinance_cache, get_yfinance_session
from utils.logger import logger

NSE_HOME_URL = "https://www.nseindia.com"
NSE_OPTION_CHAIN_URL = "https://www.nseindia.com/api/option-chain-equities?symbol={symbol}"


def _symbol_root(symbol: str) -> str:
    return str(symbol or "").split(".")[0].upper()


def _nse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": NSE_HOME_URL,
        }
    )
    return session


def _fetch_nse_options(symbol: str) -> dict | None:
    root = _symbol_root(symbol)
    if not root:
        return None
    try:
        session = _nse_session()
        session.get(NSE_HOME_URL, timeout=8)
        response = session.get(NSE_OPTION_CHAIN_URL.format(symbol=root), timeout=8)
        response.raise_for_status()
        payload = response.json()
        records = payload.get("records", {}) if isinstance(payload, dict) else {}
        rows = records.get("data", []) or []
        expiry_dates = records.get("expiryDates", []) or []
        nearest_expiry = expiry_dates[0] if expiry_dates else ""
        if nearest_expiry:
            rows = [row for row in rows if row.get("expiryDate") == nearest_expiry]

        call_oi = put_oi = call_change = put_change = 0.0
        iv_values = []
        strike_rows = []
        for row in rows:
            strike = float(row.get("strikePrice", 0) or 0)
            ce = row.get("CE") or {}
            pe = row.get("PE") or {}
            ce_oi = float(ce.get("openInterest", 0) or 0)
            pe_oi = float(pe.get("openInterest", 0) or 0)
            call_oi += ce_oi
            put_oi += pe_oi
            call_change += float(ce.get("changeinOpenInterest", 0) or 0)
            put_change += float(pe.get("changeinOpenInterest", 0) or 0)
            for side in (ce, pe):
                iv = float(side.get("impliedVolatility", 0) or 0)
                if iv:
                    iv_values.append(iv)
            if strike:
                strike_rows.append((strike, ce_oi, pe_oi))

        if call_oi <= 0 and put_oi <= 0:
            return None

        max_pain = 0
        if strike_rows:
            pain_by_strike = []
            for candidate, _, _ in strike_rows:
                total_pain = sum(
                    max(0, strike - candidate) * ce_oi
                    + max(0, candidate - strike) * pe_oi
                    for strike, ce_oi, pe_oi in strike_rows
                )
                pain_by_strike.append((candidate, total_pain))
            max_pain = min(pain_by_strike, key=lambda item: item[1])[0]
        return {
            "pcr": round(put_oi / call_oi, 2) if call_oi else 1.0,
            "max_pain": round(float(max_pain), 2) if max_pain else 0,
            "call_oi": round(call_oi, 2),
            "put_oi": round(put_oi, 2),
            "call_oi_change": round(call_change, 2),
            "put_oi_change": round(put_change, 2),
            "iv": round(sum(iv_values) / len(iv_values), 2) if iv_values else 0,
            "expiry": nearest_expiry,
            "source": "nse_option_chain",
            "data_quality": "real",
        }
    except Exception as exc:
        logger.error(f"NSE options fetch failed for {symbol}: {exc}")
        return None


def get_options_data(
    symbol
):
    """
    Fetch options chain data.
    Replace with NSE/Broker API later.
    """

    try:
        ensure_yfinance_cache()
        cache_key = f"{symbol}|options"
        cached = load_cache("options", cache_key, OPTIONS_CACHE_TTL)
        if isinstance(cached, dict) and cached:
            return cached.copy()

        nse_options = _fetch_nse_options(symbol)
        if nse_options:
            save_cache("options", cache_key, nse_options)
            return nse_options

        ticker = yf.Ticker(symbol, session=get_yfinance_session())
        expiries = list(getattr(ticker, "options", []) or [])
        if not expiries:
            return {
                "pcr": 1.0,
                "max_pain": 0,
                "call_oi": 0,
                "put_oi": 0,
                "call_oi_change": 0,
                "put_oi_change": 0,
                "iv": 0,
                "source": "unavailable",
                "data_quality": "missing",
            }

        chain = ticker.option_chain(expiries[0])
        calls = chain.calls if hasattr(chain, "calls") else pd.DataFrame()
        puts = chain.puts if hasattr(chain, "puts") else pd.DataFrame()

        call_oi = float(calls.get("openInterest", pd.Series(dtype=float)).fillna(0).sum())
        put_oi = float(puts.get("openInterest", pd.Series(dtype=float)).fillna(0).sum())
        call_volume = float(calls.get("volume", pd.Series(dtype=float)).fillna(0).sum())
        put_volume = float(puts.get("volume", pd.Series(dtype=float)).fillna(0).sum())
        pcr = round((put_oi / call_oi), 2) if call_oi else 1.0

        pain_candidates = []
        if not calls.empty and not puts.empty and "strike" in calls.columns and "strike" in puts.columns:
            strikes = sorted(set(calls["strike"]).intersection(set(puts["strike"])))
            for strike in strikes:
                call_loss = ((calls["strike"] - strike).clip(lower=0) * calls.get("openInterest", 0)).sum()
                put_loss = ((strike - puts["strike"]).clip(lower=0) * puts.get("openInterest", 0)).sum()
                pain_candidates.append((strike, call_loss + put_loss))
        max_pain = pain_candidates and min(pain_candidates, key=lambda item: item[1])[0] or 0

        call_iv = calls.get("impliedVolatility", pd.Series(dtype=float)).fillna(0)
        put_iv = puts.get("impliedVolatility", pd.Series(dtype=float)).fillna(0)
        iv_values = pd.concat([call_iv, put_iv]) if not call_iv.empty or not put_iv.empty else pd.Series(dtype=float)
        iv = round(float(iv_values.replace([float("inf")], 0).fillna(0).mean()) * 100, 2) if not iv_values.empty else 0

        options_data = {
            "pcr": pcr,
            "max_pain": round(float(max_pain), 2) if max_pain else 0,
            "call_oi": round(call_oi, 2),
            "put_oi": round(put_oi, 2),
            "call_oi_change": round(call_volume, 2),
            "put_oi_change": round(put_volume, 2),
            "iv": iv,
            "expiry": expiries[0],
            "source": "yfinance",
            "data_quality": "real",
        }
        save_cache("options", cache_key, options_data)
        return options_data

    except Exception as e:

        logger.error(
            f"Options data failed: {e}"
        )

        return {
            "pcr": 1.0,
            "max_pain": 0,
            "call_oi": 0,
            "put_oi": 0,
            "call_oi_change": 0,
            "put_oi_change": 0,
            "iv": 0,
            "source": "error",
            "data_quality": "missing",
        }
