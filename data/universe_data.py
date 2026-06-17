from __future__ import annotations

from pathlib import Path

import requests

from config import UNIVERSE_CACHE_TTL
from data.cache_utils import load_cache, save_cache
from utils.logger import logger


NSE_HOME_URL = "https://www.nseindia.com"
NSE_PREOPEN_ALL_URL = "https://www.nseindia.com/api/market-data-pre-open?key=ALL"


def _build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/html,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": NSE_HOME_URL,
        }
    )
    return session


def fetch_nse_universe(force_refresh: bool = False) -> list[str]:
    """
    Fetch NSE symbols using the exchange pre-open universe feed.
    """

    cache_key = "nse_universe_all"
    if not force_refresh:
        cached_symbols = load_cache("universe", cache_key, UNIVERSE_CACHE_TTL)
        if isinstance(cached_symbols, list) and cached_symbols:
            return cached_symbols

    try:
        session = _build_session()
        session.get(NSE_HOME_URL, timeout=15)
        response = session.get(NSE_PREOPEN_ALL_URL, timeout=30)
        response.raise_for_status()
        payload = response.json()
        symbols: list[str] = []

        for item in payload.get("data", []):
            metadata = item.get("metadata", {}) or {}
            symbol = str(metadata.get("symbol", "")).strip()
            if not symbol:
                continue
            if "." not in symbol:
                symbol = f"{symbol}.NS"
            symbols.append(symbol)

        deduped = sorted(set(symbols))
        if deduped:
            save_cache("universe", cache_key, deduped)
        return deduped

    except Exception as exc:
        logger.error(f"NSE universe fetch failed: {exc}")
        cached_symbols = load_cache("universe", cache_key, -1)
        if isinstance(cached_symbols, list) and cached_symbols:
            return cached_symbols
        return []


def write_symbols_file(output_path: str | Path, symbols: list[str]) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(symbols) + "\n", encoding="utf-8")
    return path
