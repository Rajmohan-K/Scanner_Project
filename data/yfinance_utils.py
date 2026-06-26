import os
import logging
from pathlib import Path
from tempfile import gettempdir

import requests
from urllib3.util import Retry
from requests.adapters import HTTPAdapter


_CACHE_READY = False
_YF_SESSION = None


def get_yfinance_session() -> requests.Session:
    """
    Get or create a thread-safe, browser-impersonating requests.Session
    configured with standard headers and a retry strategy with backoff.
    """
    global _YF_SESSION
    if _YF_SESSION is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        })
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        _YF_SESSION = session
    return _YF_SESSION


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

    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    logging.getLogger("yfinance").disabled = True

    import yfinance as yf
    cache_dir = Path(gettempdir()) / "scanner_project_yf_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(cache_dir))
    _CACHE_READY = True
