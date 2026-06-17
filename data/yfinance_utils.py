import os
from pathlib import Path
from tempfile import gettempdir

import yfinance as yf


_CACHE_READY = False


def _clear_dead_local_proxy() -> None:
    dead_proxy_values = {"http://127.0.0.1:9", "https://127.0.0.1:9"}
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        value = os.environ.get(key, "").strip().lower()
        if value in dead_proxy_values:
            os.environ.pop(key, None)


def ensure_yfinance_cache() -> None:
    """
    Point yfinance's timezone cache at a writable folder in this project.
    """

    global _CACHE_READY
    _clear_dead_local_proxy()

    if _CACHE_READY:
        return

    cache_dir = Path(gettempdir()) / "scanner_project_yf_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(cache_dir))
    _CACHE_READY = True
